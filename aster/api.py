"""Single-user local dashboard API; all scientific decisions use campaign.py."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from rdkit import Chem
from rdkit.Chem import Draw

from . import campaign
from .acquisition import nearest_measured
from .data import fingerprints

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(state):
    return hashlib.sha256(campaign.encoded(state).encode()).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(campaign.encoded(value))
    temporary.replace(path)


class CreateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    assay: str = Field(min_length=1, max_length=250)
    endpoint: str
    measured_csv: str = Field(max_length=2_000_000)
    candidates_csv: str = Field(max_length=2_000_000)


class ConstraintInput(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=2000)
    mode: str
    revision: str


class PreviewInput(BaseModel):
    batch_size: int = Field(default=8, ge=1, le=64)


class CommitInput(BaseModel):
    preview_id: str


class ResultsInput(BaseModel):
    csv: str = Field(max_length=2_000_000)


def create_app(storage=None):
    store = Path(storage or os.environ.get('ASTER_STORAGE', ROOT/'artifacts/dashboard')).resolve()
    store.mkdir(parents=True, exist_ok=True)
    jobs = store/'jobs'
    jobs.mkdir(exist_ok=True)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='aster-model')
    submission_lock = threading.Lock()
    # A prior process may have exited before completing a job. Never leave it spinning forever.
    for path in jobs.glob('*.json'):
        job = json.loads(path.read_text())
        if job['status'] in ('queued', 'running'):
            job.update(status='failed', error='Server restarted. Preview again; no batch was committed.')
            atomic_json(path, job)

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=True)

    app = FastAPI(title='Aster local campaign API', version='0.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def local_requests(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:3001', 'http://127.0.0.1:3001'):
            return JSONResponse({'detail': 'This prototype accepts local requests only'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({'detail': str(error)}, status_code=422)

    def identifier(value):
        if not re.fullmatch(r'[a-f0-9]{32}', value):
            raise HTTPException(404, 'Unknown identifier')
        return value

    def database(cid):
        path = store/(identifier(cid)+'.sqlite')
        if not path.is_file():
            raise HTTPException(404, 'Campaign not found')
        return path

    def read_job(jid):
        path = jobs/(identifier(jid)+'.json')
        if not path.is_file():
            raise HTTPException(404, 'Job not found')
        return json.loads(path.read_text())

    def create_record(body, demo=False):
        cid = uuid4().hex
        with tempfile.TemporaryDirectory() as tmp:
            measured, candidates = Path(tmp)/'measured.csv', Path(tmp)/'candidates.csv'
            measured.write_text(body.measured_csv)
            candidates.write_text(body.candidates_csv)
            for path in (measured, candidates):
                if sum(1 for _ in csv.DictReader(path.open())) > 2000:
                    raise ValueError('Prototype limit: 2,000 rows per input CSV')
            campaign.create(store/(cid+'.sqlite'), measured, candidates, name=body.name, assay=body.assay, endpoint=body.endpoint)
        if demo:
            with campaign.transaction(store/(cid+'.sqlite'), True) as state:
                state['demo'] = True
        return {'id': cid}

    def compute_preview(cid, jid, size):
        path = jobs/(jid+'.json')
        job = read_job(jid)
        job.update(status='running')
        atomic_json(path, job)
        try:
            state = campaign.load(database(cid))
            revision = fingerprint(state)
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp)/'preview.sqlite'
                with sqlite3.connect(copy) as connection:
                    connection.execute('CREATE TABLE campaign(id INTEGER PRIMARY KEY, payload TEXT)')
                    connection.execute('INSERT INTO campaign VALUES(1, ?)', (campaign.encoded(state),))
                record = campaign.propose(copy, size)
            # Score all currently available candidates for the map, including excluded ones.
            ids = sorted(k for k, v in state['compounds'].items() if v['status'] == 'available')
            observed = record['training']
            x = fingerprints([r['smiles'] for r in observed])
            scored = []
            for start in range(0, len(ids), 256):
                chunk = ids[start:start+256]
                features = fingerprints([state['compounds'][c]['smiles'] for c in chunk])
                values = features @ np.asarray(record['model']['coefficients']) + record['model']['intercept']
                nearest, novelty = nearest_measured(features, x)
                for index, cid2 in enumerate(chunk):
                    neighbor = observed[int(nearest[index])]
                    scored.append({'compound_id': cid2, 'prediction': float(values[index]),
                                   'similarity': float(1-novelty[index]), 'nearest_measured_id': neighbor['compound_id'],
                                   'nearest_measured_value': neighbor['value'], 'constraint': state['compounds'][cid2]['constraint']})
            preview = {'id': jid, 'campaign_id': cid, 'revision': revision, 'record': record, 'scored': scored}
            atomic_json(store/(jid+'.preview.json'), preview)
            job.update(status='complete', preview_id=jid)
        except Exception as error:
            job.update(status='failed', error=str(error))
        atomic_json(path, job)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'local-research-prototype'}

    @app.get('/campaigns')
    def list_campaigns():
        return [{'id': p.stem, **campaign.summary(p)} for p in sorted(store.glob('*.sqlite'), key=lambda p: p.stat().st_mtime, reverse=True)]

    @app.post('/campaigns', status_code=201)
    def create_campaign(body: CreateInput):
        return create_record(body)

    @app.post('/demo', status_code=201)
    def demo():
        fixture = ROOT/'examples/dashboard'
        return create_record(CreateInput(name='Dopamine transporter · public replay', assay='MoleculeACE CHEMBL238 Ki task', endpoint='pKi',
                                         measured_csv=(fixture/'measured.csv').read_text(), candidates_csv=(fixture/'candidates.csv').read_text()), demo=True)

    @app.get('/campaigns/{cid}')
    def get_campaign(cid: str):
        state = campaign.load(database(cid))
        rounds = [{k: r[k] for k in ('round', 'status', 'created_at', 'recommendations', 'results', 'training_sha256')} |
                  {'training_count': len(r['training']), 'preview_id': r.get('preview_id')} for r in state['rounds']]
        return {'id': cid, 'revision': fingerprint(state), 'name': state['name'], 'assay': state['assay'], 'endpoint': state['endpoint'],
                'demo': state.get('demo', False), 'recipe': state['recipe'], 'rounds': rounds, 'events': state['events'],
                'compounds': [{'compound_id': key, **value} for key, value in state['compounds'].items()]}

    @app.get('/campaigns/{cid}/replay')
    def replay(cid: str):
        from .replay import replay_manifest
        return replay_manifest(database(cid), store)

    @app.post('/campaigns/{cid}/constraints')
    def constraints(cid: str, body: ConstraintInput):
        # Serialize revision check and update together; never acquire a second writer lock.
        with campaign.transaction(database(cid), True) as state:
            if fingerprint(state) != body.revision:
                raise HTTPException(409, 'Campaign changed. Reload before editing constraints.')
            if body.mode not in ('available', 'locked', 'excluded') or len(set(body.ids)) != len(body.ids):
                raise ValueError('Invalid constraint')
            for compound_id in body.ids:
                if compound_id not in state['compounds'] or state['compounds'][compound_id]['status'] != 'available':
                    raise ValueError('Only available candidates can be locked or excluded')
            for compound_id in body.ids:
                state['compounds'][compound_id]['constraint'] = body.mode
            campaign.event(state, 'constraints', {'ids': body.ids, 'mode': body.mode})
        return {'ok': True}

    @app.post('/campaigns/{cid}/previews', status_code=202)
    def preview(cid: str, body: PreviewInput):
        state = campaign.load(database(cid))
        if any(r['status'] == 'pending' for r in state['rounds']):
            raise HTTPException(409, 'Finish the pending batch before creating another preview')
        with submission_lock:
            for path in jobs.glob('*.json'):
                job = json.loads(path.read_text())
                if job['campaign_id'] == cid and job['status'] in ('queued', 'running'):
                    return {'job_id': job['id']}
            jid = uuid4().hex
            atomic_json(jobs/(jid+'.json'), {'id': jid, 'campaign_id': cid, 'status': 'queued', 'created_at': campaign.stamp()})
            executor.submit(compute_preview, cid, jid, body.batch_size)
        return {'job_id': jid}

    @app.get('/jobs/{jid}')
    def job(jid: str):
        return read_job(jid)

    @app.get('/campaigns/{cid}/previews/{pid}')
    def get_preview(cid: str, pid: str):
        database(cid)
        path = store/(identifier(pid)+'.preview.json')
        if not path.is_file():
            raise HTTPException(404, 'Preview is not ready')
        result = json.loads(path.read_text())
        if result['campaign_id'] != cid:
            raise HTTPException(404, 'Preview does not belong to this campaign')
        record = result.pop('record')
        return {**result, 'recommendations': record['recommendations'], 'training_count': len(record['training']), 'round': record['round']}

    @app.post('/campaigns/{cid}/commit')
    def commit(cid: str, body: CommitInput):
        path = store/(identifier(body.preview_id)+'.preview.json')
        if not path.is_file():
            raise HTTPException(404, 'Preview not found')
        preview = json.loads(path.read_text())
        if preview['campaign_id'] != cid:
            raise HTTPException(404, 'Preview does not belong to this campaign')
        with campaign.transaction(database(cid), True) as state:
            for record in state['rounds']:
                if record.get('preview_id') == body.preview_id:
                    return {'round': record['round'], 'already_committed': True}
            if fingerprint(state) != preview['revision']:
                raise HTTPException(409, 'Preview is stale. Generate a fresh preview before committing.')
            record = preview['record']
            record['preview_id'] = body.preview_id
            for row in record['recommendations']:
                state['compounds'][row['compound_id']]['status'] = 'pending'
            state['rounds'].append(record)
            campaign.event(state, 'commit', {'round': record['round'], 'preview_id': body.preview_id,
                                           'training_sha256': record['training_sha256']})
        return {'round': record['round'], 'already_committed': False}

    @app.get('/campaigns/{cid}/rounds/{number}/export')
    def export(cid: str, number: int, template: bool = False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'batch.csv'
            campaign.export_batch(database(cid), number, path, template)
            return Response(path.read_text(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="aster-round-{number}{"-results" if template else "-batch"}.csv"'})

    def add_results(cid, number, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'results.csv'
            path.write_text(text)
            return campaign.import_results(database(cid), number, path)

    @app.post('/campaigns/{cid}/rounds/{number}/results')
    def results(cid: str, number: int, body: ResultsInput):
        return add_results(cid, number, body.csv)

    @app.post('/campaigns/{cid}/rounds/{number}/demo-results')
    def demo_results(cid: str, number: int):
        state = campaign.load(database(cid))
        if not state.get('demo') or not 1 <= number <= len(state['rounds']):
            raise HTTPException(404, 'Public replay outcomes are unavailable for this campaign')
        with (ROOT/'examples/dashboard/outcomes.csv').open() as handle:
            lookup = {r['compound_id']: r['value'] for r in csv.DictReader(handle)}
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=['compound_id', 'status', 'value'])
        writer.writeheader()
        writer.writerows({'compound_id': r['compound_id'], 'status': 'measured', 'value': lookup[r['compound_id']]}
                         for r in state['rounds'][number-1]['recommendations'])
        return add_results(cid, number, buffer.getvalue())

    @app.get('/campaigns/{cid}/molecule')
    def molecule(cid: str, compound_id: str):
        state = campaign.load(database(cid))
        if compound_id not in state['compounds']:
            raise HTTPException(404, 'Compound not found')
        mol = Chem.MolFromSmiles(state['compounds'][compound_id]['smiles'])
        drawer = Draw.MolDraw2DSVG(360, 200)
        drawer.drawOptions().clearBackground = False
        Draw.rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        drawer.FinishDrawing()
        return Response(drawer.GetDrawingText(), media_type='image/svg+xml')

    return app


app = create_app()
