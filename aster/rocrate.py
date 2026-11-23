"""Package a campaign for archiving as an RO-Crate, with W3C PROV provenance.

An RO-Crate (Research Object Crate, https://w3id.org/ro/crate/1.1) is a directory of
files plus one `ro-crate-metadata.json` that describes them in JSON-LD, using
schema.org terms. W3C PROV-O (https://www.w3.org/TR/prov-o/) is the standard
vocabulary for "what was made from what, by which process, run by whom": entities,
activities and agents, joined by `used`, `wasGeneratedBy` and `wasAssociatedWith`.

The mapping into PROV is the one the Argonne profile states (arXiv:2608.18312, sec. 4.2):
"mapping individuals to entities, operators to activities, streams or humans to agents,
and parent-child edges to usage/generation relations". Each operator is also a
schema.org `CreateAction`, which is how RO-Crate itself describes a process that turned
inputs (`object`) into outputs (`result`).

The paper gives no PROV mapping for fitness records, evidence bindings, archive events
or steering commands, and warns that this is where meaning is lost: they "should be
preserved as explicit fields or companion files rather than compressed into free text
metadata". So they are not squeezed into the metadata graph. They travel whole, in
`events.jsonl`, which the metadata describes as a file of the crate.

Files written:

    ro-crate-metadata.json   the description, with the PROV graph
    events.jsonl             every event, one JSON object per line (aster/event_log.py)
    invariants.json          the profile's five invariants, tested against those events
    decision-record.json     every decision, as `python -m aster.decisions record` prints it
    campaign.json            the campaign exactly as stored, the source of all the above
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .campaign import declaration, load
from .decisions import record as decision_record
from .event_log import PROFILE, PERSON, SELECTION, check, events

CRATE_SPEC = 'https://w3id.org/ro/crate/1.1'
CONTEXT = [f'{CRATE_SPEC}/context',
           {'prov': 'http://www.w3.org/ns/prov#',
            # Ad hoc terms, as RO-Crate allows, for the few things schema.org lacks.
            'aster': 'https://github.com/aster-build/aster/blob/main/docs/VOCABULARY.md#',
            'sha256': 'aster:sha256',
            'payloadHash': 'aster:payloadHash',
            'recordKind': 'aster:recordKind'}]
FILES = {
    'events.jsonl': ('application/x-ndjson', 'Append-only event log in the Argonne profile record types'),
    'invariants.json': ('application/json', "The profile's five invariants tested against events.jsonl"),
    'decision-record.json': ('application/json', 'Every selection decision joined to its basis and outcome'),
    'campaign.json': ('application/json', 'The campaign exactly as Aster stored it'),
}


def _dump(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'


def _iri(ident):
    """A local identifier for an event id. Compound and assay names can hold spaces or
    other characters an IRI cannot, so they are percent-encoded; the event log keeps the
    original id, and `identifier` on each entity carries it too."""
    return '#' + quote(ident, safe=':_-.~')


def _ref(ident):
    return {'@id': _iri(ident)}


def _refs(idents):
    """One reference, or a list of several: RO-Crate 1.1 asks for no singleton arrays."""
    refs = [_ref(i) for i in idents]
    return refs[0] if len(refs) == 1 else refs


def _agent(row, state):
    stream = row['id']
    if stream == SELECTION:
        return {'@id': _iri(stream), 'identifier': stream, '@type': ['SoftwareApplication', 'prov:Agent'],
                'name': 'Aster selection policy',
                'softwareVersion': _version(), 'description': row['note']}
    if stream == PERSON:
        return {'@id': _iri(stream), 'identifier': stream, '@type': ['Person', 'prov:Agent'],
                'name': 'A person using Aster (identity not recorded)', 'description': row['note']}
    return {'@id': _iri(stream), 'identifier': stream, '@type': ['Thing', 'prov:Agent'],
            'name': f"Assay {state['assay']}", 'description': row['note']}


def _version():
    try:
        return importlib.metadata.version('aster-discovery')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def metadata(state, rows, files, *, license=None):
    """The JSON-LD description of the crate, PROV graph included."""
    graph = [{'@id': 'ro-crate-metadata.json', '@type': 'CreativeWork',
              'conformsTo': {'@id': CRATE_SPEC}, 'about': {'@id': './'}}]
    declared = declaration(state)
    root = {'@id': './', '@type': 'Dataset', 'name': f"Aster campaign: {state['name']}",
            'description': (f"Selection decisions for the assay {state['assay']!r} on the endpoint "
                            f"{declared['endpoint']} ({declared['direction'].replace('_', ' ')}), "
                            'with the provenance of every batch.'),
            'datePublished': datetime.now(timezone.utc).date().isoformat(),
            'dateCreated': state['created_at'],
            'hasPart': [{'@id': name} for name in files],
            'mentions': [], 'conformsTo': {'@id': PROFILE['url']}}
    if license:
        root['license'] = {'@id': license}
    graph.append(root)
    graph.append({'@id': PROFILE['url'], '@type': 'CreativeWork', 'name': PROFILE['name'],
                  'citation': PROFILE['citation']})
    for name, (fmt, description) in FILES.items():
        graph.append({'@id': name, '@type': 'File', 'name': name, 'description': description,
                      'encodingFormat': fmt, 'contentSize': str(files[name]['size']),
                      'sha256': files[name]['sha256']})
    generated = {}
    for row in rows:
        if row['record_type'] == 'operator':
            for child in row['child_ids']:
                generated.setdefault(child, []).append(row['id'])
    for row in rows:
        if row['record_type'] == 'run_and_stream' and row.get('stream_id'):
            graph.append(_agent(row, state))
        elif row['record_type'] == 'individual' and row['kind'] != 'claim':
            # Claims are evidence-bound statements, not derived artifacts; they stay in
            # events.jsonl with their bindings rather than becoming bare PROV entities.
            entity = {'@id': _iri(row['id']), 'identifier': row['id'], '@type': ['Thing', 'prov:Entity'],
                      'name': row['id'].split(':', 1)[1] if row['kind'] == 'molecule' else row['id'],
                      'recordKind': row['kind'], 'payloadHash': row['payload_hash'],
                      'dateCreated': row['created_at']}
            if row.get('note'):
                entity['description'] = row['note']
            if row['id'] in generated:
                entity['prov:wasGeneratedBy'] = _refs(generated[row['id']])
            graph.append(entity)
        elif row['record_type'] == 'operator':
            action = {'@id': _iri(row['id']), 'identifier': row['id'], '@type': ['CreateAction', 'prov:Activity'],
                      'name': row['op_type'], 'endTime': row['timestamp'],
                      'agent': _ref(row['emitter_stream']),
                      'object': _refs(row['parent_ids']),
                      'result': _refs(row['child_ids']),
                      'prov:used': _refs(row['parent_ids']),
                      'prov:wasAssociatedWith': _ref(row['emitter_stream'])}
            if row.get('note'):
                action['description'] = row['note']
            graph.append(action)
            root['mentions'].append(_ref(row['id']))
    return {'@context': CONTEXT, '@graph': graph}


def write(path_or_state, directory, *, license=None):
    """Write the crate into a new, empty directory and return what was written."""
    state = path_or_state if isinstance(path_or_state, dict) else load(path_or_state)
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f'Refusing to write a crate into a non-empty directory: {directory}')
    directory.mkdir(parents=True, exist_ok=True)
    rows = events(state)
    report = check(rows)
    contents = {'events.jsonl': ''.join(json.dumps(row, sort_keys=True, allow_nan=False) + '\n'
                                        for row in rows),
                'invariants.json': _dump(report),
                'decision-record.json': _dump(decision_record(state)),
                'campaign.json': _dump(state)}
    files = {}
    for name, text in contents.items():
        data = text.encode()
        (directory/name).write_bytes(data)
        files[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (directory/'ro-crate-metadata.json').write_text(_dump(metadata(state, rows, files, license=license)))
    return {'directory': str(directory), 'files': ['ro-crate-metadata.json', *files],
            'events': len(rows), 'invariants_hold': all(i['holds'] is not False for i in report['invariants']),
            'license': license or 'none declared; pass one before publishing the crate'}
