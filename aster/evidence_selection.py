"""Milestone 9, first hypothesis: does permitted external evidence improve selection?

The study compares three arms under identical splits, seeds and acquisition budgets:
campaign measurements alone, campaign measurements plus permitted external
measurements, and an information-matched control whose external values are permuted.
Evidence enters only this offline research path; the product default is unchanged.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark import load_task, split_case
from .data import digest, fingerprints, write_json
from .evidence import canonical
from .experiment import LabelOracle
from .heads import StableRidge

CONFLICT_TOLERANCE = 0.5
PACKAGES = ('numpy', 'pandas', 'scikit-learn', 'rdkit')


def seal(out: Path, inputs: dict) -> None:
    """Record inputs, library versions and module hashes before the study runs."""
    out.mkdir(parents=True, exist_ok=True)
    contract = {'inputs': inputs,
                'versions': {name: importlib.metadata.version(name) for name in PACKAGES},
                'source_hashes': {path.name: digest(path)
                                  for path in sorted(Path(__file__).parent.glob('*.py'))}}
    path = out / 'contract.json'
    if path.exists() and json.loads(path.read_text()) != contract:
        raise ValueError('Contract changed; use a new output directory')
    write_json(path, contract)


def to_pki(value: float, unit: str) -> float:
    """Only exact nanomolar concentrations are converted; nothing else is guessed."""
    if unit != 'nM' or not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f'Unsupported evidence unit: {unit}')
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Evidence concentrations must be positive and finite')
    return 9.0 - math.log10(value)


def external_measurements(corpus: Path, study: dict) -> tuple[pd.DataFrame, dict]:
    """Keep exact, equality-relation measurements of the declared target and endpoint."""
    records = json.loads(Path(corpus).read_text())
    rows, dropped = [], {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for record in records:
        if record.get('target_accession') != study['target_accession']:
            drop('other_target')
        elif record.get('endpoint') != study['endpoint']:
            drop('other_endpoint')
        elif record.get('retracted'):
            drop('retracted')
        elif record.get('evidence_type') != 'experimental':
            drop('not_experimental')
        elif record.get('value') is None or record.get('compound_smiles') is None:
            drop('no_measurement_or_structure')
        elif record.get('relation') != '=':
            drop('censored_relation')
        else:
            rows.append({'identity': canonical(record['compound_smiles']),
                         'value': to_pki(record['value'], record['unit']),
                         'document_id': record.get('resolved_document_id') or record['document_id'],
                         'source_sha256': record['source_sha256'],
                         'review_status': record['review_status'],
                         'review_method': record.get('review_method', 'unspecified')})
    frame = pd.DataFrame(rows, columns=['identity', 'value', 'document_id', 'source_sha256',
                                        'review_status', 'review_method'])
    # Disagreeing measurements of one structure are excluded, never averaged.
    spread = frame.groupby('identity').value.agg(lambda v: float(v.max() - v.min()))
    conflicting = set(spread[spread > CONFLICT_TOLERANCE].index)
    dropped['conflicting_values'] = int(frame.identity.isin(conflicting).sum())
    frame = frame[~frame.identity.isin(conflicting)]
    merged = frame.groupby('identity', as_index=False).agg(
        value=('value', 'mean'), replicates=('value', 'size'),
        documents=('document_id', lambda v: ';'.join(sorted(set(v)))))
    audit = {'records_in_corpus': len(records), 'dropped': dropped,
             'eligible_measurements': len(frame), 'unique_structures': len(merged),
             'replicate_structures_averaged_within_tolerance':
                 int((merged.replicates > 1).sum()),
             'structures_by_review_method':
                 {method: int(group.identity.nunique())
                  for method, group in frame.groupby('review_method')},
             'human_reviewed_structures':
                 int(frame[frame.review_method == 'human'].identity.nunique()),
             'conversion': 'pKi = 9 - log10(Ki in nM)',
             'conflict_tolerance_log_units': CONFLICT_TOLERANCE}
    return merged, audit


def permitted(evidence: pd.DataFrame, frame: pd.DataFrame, case: dict) -> tuple[pd.DataFrame, dict]:
    """Strict replay: an external structure present anywhere in the task is withheld."""
    in_task = set(frame.identity)
    keep = evidence[~evidence.identity.isin(in_task)].reset_index(drop=True)
    hidden = set(frame.iloc[case['pool'] + case['audit']].identity)
    if set(keep.identity) & hidden:
        raise ValueError('Permitted evidence overlaps a withheld compound; aborting')
    return keep, {'permitted_structures': len(keep),
                  'withheld_because_present_in_task': int(evidence.identity.isin(in_task).sum()),
                  'withheld_because_in_pool_or_audit':
                      int(evidence.identity.isin(hidden).sum())}


def replay(x, audit_x, oracle, initial, study, seed, extra_x, extra_y):
    """Greedy Morgan + ridge, with optional fixed external rows added to every fit."""
    observed = np.asarray(initial, dtype=int).copy()
    values = oracle.reveal(observed)
    remaining = np.setdiff1d(np.arange(len(x)), observed)
    low, high = study['prediction_guard']
    picks, history, outside = [], [], 0
    for round_i in range(study['rounds'] + 1):
        features = np.vstack([x[observed], extra_x]) if len(extra_x) else x[observed]
        targets = np.concatenate([values, extra_y]) if len(extra_x) else values
        model = StableRidge(study['scaling'], study['ridge_alpha']).fit(features, targets)
        audit_prediction = model.predict(audit_x)
        if not np.isfinite(audit_prediction).all():
            raise ValueError('Nonfinite audit prediction')
        outside += int(((audit_prediction < low) | (audit_prediction > high)).sum())
        history.append({'round': round_i, 'training_size': len(observed),
                        'external_rows': int(len(extra_x)),
                        'audit_prediction': audit_prediction.tolist()})
        if round_i == study['rounds']:
            break
        pool_prediction = model.predict(x[remaining])
        outside += int(((pool_prediction < low) | (pool_prediction > high)).sum())
        order = np.lexsort((remaining, -pool_prediction))[:study['batch_size']]
        selected = remaining[order]
        for rank, index in enumerate(order, 1):
            picks.append({'round': round_i + 1, 'rank': rank, 'index': int(remaining[index]),
                          'prediction': float(pool_prediction[index])})
        measured = oracle.reveal(selected)
        observed = np.concatenate([observed, selected])
        values = np.concatenate([values, measured])
        remaining = np.setdiff1d(remaining, selected)
    return {'picks': picks, 'history': history, 'outside_guard': outside}


def score(frame, case, result, study):
    """Evaluator: hidden outcomes are read only after the replay has finished."""
    working = case['initial'] + case['pool']
    actual = frame.iloc[case['audit']].value.to_numpy()
    cutoff = float(np.quantile(frame.iloc[case['pool']].value, 0.9))
    initial_scaffolds = set(frame.iloc[case['initial']].scaffold)
    for pick in result['picks']:
        row = frame.iloc[working[pick['index']]]
        pick['compound_id'] = row.compound_id
        pick['top_decile'] = bool(row.value >= cutoff)
        pick['hit'] = bool(row.value >= study['hit_threshold_pki'])
        pick['scaffold'] = row.scaffold
    final = result['history'][-1]
    error = np.abs(np.asarray(final['audit_prediction']) - actual)
    scaffolds = {pick['scaffold'] for pick in result['picks']}
    return {'top_decile_found': sum(pick['top_decile'] for pick in result['picks']),
            'additional_hits': sum(pick['hit'] for pick in result['picks']),
            'novel_scaffolds': len(scaffolds - initial_scaffolds),
            'audit_mae': float(error.mean()),
            'top_decile_threshold': cutoff,
            'outside_guard': result['outside_guard'],
            'external_rows': final['external_rows']}


def run(study_path: Path, raw: Path, out: Path) -> None:
    study = json.loads(Path(study_path).read_text())
    task = {'id': study['task'], 'sha256': study['task_sha256']}
    frame, provenance = load_task(Path(raw) / f"{study['task']}.csv", task)
    evidence, evidence_audit = external_measurements(Path(study['corpus']), study)
    seal(Path(out), {'study': digest(Path(study_path)), 'study_version': study['version'],
                     'task': study['task'], 'task_sha256': study['task_sha256'],
                     'corpus_sha256': digest(Path(study['corpus'])),
                     'arms': [arm['id'] for arm in study['arms']]})
    out = Path(out)
    write_json(out / 'evidence_audit.json', evidence_audit)
    write_json(out / 'task_provenance.json', provenance)

    x = fingerprints(frame.smiles.tolist(), study['radius'], study['bits'])
    evidence_x = fingerprints(evidence.identity.tolist(), study['radius'], study['bits']) \
        if len(evidence) else np.zeros((0, study['bits']), dtype=np.uint8)
    rows, filters = [], {}
    for protocol in study['protocols']:
        for size in study['support_sizes']:
            for seed in study['seeds']:
                case = split_case(frame, protocol, seed, size)
                keep, filtered = permitted(evidence, frame, case)
                filters[f'{protocol}:{size}:{seed}'] = filtered
                index = [evidence.index[evidence.identity == i][0] for i in keep.identity]
                kept_x = evidence_x[index] if index else evidence_x[:0]
                kept_y = keep.value.to_numpy()
                working = case['initial'] + case['pool']
                for arm in study['arms']:
                    if arm['evidence'] == 'none':
                        extra_x, extra_y = evidence_x[:0], np.zeros(0)
                    elif arm['evidence'] == 'permitted_external_measurements':
                        extra_x, extra_y = kept_x, kept_y
                    else:
                        shuffle = np.random.default_rng(
                            np.random.SeedSequence([seed, size, 909])).permutation(len(kept_y))
                        extra_x, extra_y = kept_x, kept_y[shuffle]
                    result = replay(x[working], x[case['audit']],
                                    LabelOracle(frame.iloc[working].value.to_numpy()),
                                    np.arange(size), study, seed, extra_x, extra_y)
                    rows.append({'protocol': protocol, 'support_size': size, 'seed': seed,
                                 'arm': arm['id'], **score(frame, case, result, study)})
                    print(f"{protocol} n={size} seed={seed} {arm['id']}: "
                          f"top_decile={rows[-1]['top_decile_found']}", flush=True)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(out / 'case_metrics.csv', index=False)
    write_json(out / 'evidence_filters.json', filters)
    write_json(out / 'comparison.json', compare(metrics, study))


def compare(metrics: pd.DataFrame, study: dict) -> dict:
    """Paired per-case differences against the baseline arm."""
    keys = ['protocol', 'support_size', 'seed']
    baseline = metrics[metrics.arm == 'baseline'].set_index(keys)
    report = {'cases': int(len(baseline)), 'arms': {}}
    for arm in [a['id'] for a in study['arms'] if a['id'] != 'baseline']:
        other = metrics[metrics.arm == arm].set_index(keys)
        if len(other) != len(baseline):
            raise ValueError('Unpaired arms')
        entry = {}
        for metric in ['top_decile_found', 'additional_hits', 'audit_mae']:
            delta = (other[metric] - baseline[metric]).astype(float)
            entry[metric] = {
                'baseline_mean': float(baseline[metric].mean()),
                'arm_mean': float(other[metric].mean()),
                'mean_paired_difference': float(delta.mean()),
                'standard_error': float(delta.std(ddof=1) / np.sqrt(len(delta))) if len(delta) > 1 else None,
                'better': int((delta > 0).sum()), 'unchanged': int((delta == 0).sum()),
                'worse': int((delta < 0).sum()),
                'by_protocol': {p: float(delta.xs(p, level='protocol').mean())
                                for p in study['protocols']}}
        entry['external_rows_mean'] = float(other.external_rows.mean())
        report['arms'][arm] = entry
    gate = study['promotion_gate']
    literature = report['arms']['literature_strict']['top_decile_found']['mean_paired_difference']
    control = report['arms']['shuffled_control']['top_decile_found']['mean_paired_difference']
    report['gate'] = {'mean_top_decile_gain': literature,
                      'control_gain': control,
                      'separation_from_control': literature - control,
                      'gain_threshold': gate['mean_top_decile_gain_min'],
                      'separation_threshold': gate['control_separation_min'],
                      'passes': bool(literature >= gate['mean_top_decile_gain_min']
                                     and literature - control >= gate['control_separation_min'])}
    report['conclusion'] = ('Evidence augmentation meets the predeclared gate on this target.'
                            if report['gate']['passes'] else
                            'Evidence augmentation does not meet the predeclared gate; the campaign-only '
                            'default stands for this target.')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description='Milestone 9 evidence-augmented selection study')
    parser.add_argument('--study', type=Path, default=Path('configs/evidence-v1.json'))
    parser.add_argument('--raw', type=Path, default=Path('data/moleculeace'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/evidence-v1'))
    args = parser.parse_args()
    run(args.study, args.raw, args.output)


if __name__ == '__main__':
    main()
