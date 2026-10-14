"""Read-only presentation of saved campaign decisions; never fits or selects."""
import json
from pathlib import Path
from . import campaign


def replay_manifest(database: Path, storage: Path):
    state = campaign.load(database)
    rounds = []
    for record in state['rounds']:
        scored = record['recommendations']
        coverage = 'committed batch only'
        preview_id = record.get('preview_id')
        if preview_id:
            path = storage / (preview_id + '.preview.json')
            if path.is_file():
                saved = json.loads(path.read_text())
                if saved['campaign_id'] == database.stem and saved['record']['training_sha256'] == record['training_sha256']:
                    scored = saved['scored']
                    coverage = 'saved scored pool'
        coefficients = record['model']['coefficients']
        rounds.append({
            'round': record['round'], 'status': record['status'],
            'created_at': record['created_at'], 'training_sha256': record['training_sha256'],
            'training': [{'compound_id': r['compound_id'], 'value': r['value']} for r in record['training']],
            'recipe': record['recipe'], 'eligible_count': len(record['eligible_ids']),
            'model': {'intercept': record['model']['intercept'], 'feature_count': len(coefficients),
                      'nonzero_coefficients': sum(c != 0 for c in coefficients)},
            'scored': scored, 'score_coverage': coverage,
            'recommendations': record['recommendations'], 'results': record['results'],
        })
    return {'campaign_id': database.stem, 'name': state['name'], 'endpoint': state['endpoint'],
            'assay': state['assay'], 'demo': state.get('demo', False),
            'mode': 'read-only recorded decisions', 'rounds': rounds, 'events': state['events']}
