"""Local, persisted docking jobs; no changes to campaign decisions."""
import hashlib
import json
import subprocess
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from rdkit import Chem
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/docking'

def runtime_available(): return (ROOT/'.venv-docking/bin/python').is_file()

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2)); tmp.replace(path)
def validation():
    path=BASE/'validation.json'
    if not path.exists(): return {'status':'unavailable','passed':False,'reason':'Run the 8Y2G redocking validation first.'}
    report=json.loads(path.read_text())
    report['validation_sha256']=sha(path)
    if report.get('passed'):
        for filename,expected in report['hashes'].items():
            source=ROOT/filename
            if not source.is_file() or sha(source)!=expected:
                return {**report,'status':'stale','passed':False,'reason':'Validated inputs changed. Revalidate before docking.'}
    return report

class DockingJobs:
    def __init__(self,store):
        self.store=store/'docking'; self.store.mkdir(exist_ok=True)
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='aster-docking')
        self.lock=threading.Lock()
        for path in self.store.glob('*/job.json'):
            job=json.loads(path.read_text())
            if job['status'] in ('queued','running'):
                job.update(status='failed',error='Server restarted during docking. Submit again.'); write(path,job)
    def close(self): self.executor.shutdown(wait=True)
    def list(self,cid):
        return sorted([json.loads(p.read_text()) for p in self.store.glob('*/job.json') if json.loads(p.read_text())['campaign_id']==cid],key=lambda j:j['created_at'],reverse=True)
    def get(self,cid,jid):
        if len(jid)!=32 or any(c not in '0123456789abcdef' for c in jid): raise HTTPException(404,'Unknown docking job')
        path=self.store/jid/'job.json'
        if not path.is_file(): raise HTTPException(404,'Unknown docking job')
        job=json.loads(path.read_text())
        if job['campaign_id']!=cid: raise HTTPException(404,'Unknown docking job')
        if job['status']=='complete': job['result']=json.loads((path.parent/'result.json').read_text())
        return job
    def submit(self,cid,state,compound_id):
        if not state.get('demo'): raise HTTPException(422,'This receptor is linked only to the DAT demo. Imported targets require verification.')
        compound=state['compounds'].get(compound_id)
        if compound is None: raise HTTPException(404,'Compound not found')
        report=validation()
        if not report.get('passed'): raise HTTPException(409,report['reason'])
        molecule=Chem.MolFromSmiles(compound['smiles'])
        if molecule is None or len(Chem.GetMolFrags(molecule))!=1 or molecule.GetNumHeavyAtoms()>80:
            raise HTTPException(422,'Docking supports one molecular fragment with at most 80 heavy atoms.')
        if any(s=='?' for _,s in Chem.FindMolChiralCenters(molecule,includeUnassigned=True)):
            raise HTTPException(422,'Resolve unspecified stereocenters before docking.')
        if not runtime_available(): raise HTTPException(503,'Docking environment is not installed.')
        smiles=Chem.MolToSmiles(molecule,isomericSmiles=True)
        with self.lock:
            existing=self.list(cid)
            for job in existing:
                if job['compound_id']==compound_id and job['validation_sha256']==report['validation_sha256'] and job['status']!='failed': return job
            all_jobs=[json.loads(p.read_text()) for p in self.store.glob('*/job.json')]
            if sum(j['status'] in ('queued','running') for j in all_jobs)>=4: raise HTTPException(429,'Docking queue is full (four jobs). Try again after a job finishes.')
            jid=uuid4().hex; directory=self.store/jid; directory.mkdir()
            job={'id':jid,'campaign_id':cid,'compound_id':compound_id,'smiles':smiles,'validation_sha256':report['validation_sha256'],'status':'queued','created_at':datetime.now(timezone.utc).isoformat()}
            write(directory/'request.json',job); write(directory/'job.json',job)
            self.executor.submit(self.run,jid)
            return job
    def run(self,jid):
        directory=self.store/jid; job=json.loads((directory/'job.json').read_text()); job['status']='running'; write(directory/'job.json',job)
        try:
            with (directory/'worker.log').open('w') as log:
                process=subprocess.Popen([str(ROOT/'.venv-docking/bin/python'),str(ROOT/'scripts/dock_candidate.py'),str(directory)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    code=process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL); process.wait(); raise
                if code: raise subprocess.CalledProcessError(code,process.args)
            result=json.loads((directory/'result.json').read_text())
            job.update(status='complete',valid_poses=sum(p['passed'] for p in result['poses']))
        except Exception as error:
            job.update(status='failed',error=f'Docking failed ({type(error).__name__}). Preparation or physical validation may be unsupported; inspect the saved worker log.')
        job['finished_at']=datetime.now(timezone.utc).isoformat(); write(directory/'job.json',job)
