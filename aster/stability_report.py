"""Validate completed replay artifacts and write matched, target-aware comparisons."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .data import digest, write_json


def table(frame):
    cols = list(frame.columns)
    lines = ['| ' + ' | '.join(cols) + ' |', '| ' + ' | '.join(['---']*len(cols)) + ' |']
    for row in frame.itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join(f'{v:.3f}' if isinstance(v, (float, np.floating)) else str(v) for v in row) + ' |')
    return '\n'.join(lines)


def validate(root, prepared, expected):
    plan = json.loads((prepared/'plan.json').read_text())
    contract = json.loads((root/'contract.json').read_text())
    assert contract['inputs']['plan'] == digest(prepared/'plan.json'), 'Plan changed'
    for task, sha in plan['prepared_hashes'].items():
        assert digest(prepared/f'{task}.csv') == sha, 'Prepared data changed'
    paths = sorted((root/'cases').glob('*.json'))
    records = [json.loads(p.read_text()) for p in paths]
    assert len(records) == expected, (root, len(records), expected)
    manifest = {c['id']:c for c in plan['cases']}
    checked = set()
    for r in records:
        case = manifest[r['case_id']]
        frame = pd.read_csv(prepared/f"{r['task']}.csv")
        assert r['task'] == case['task']
        for field in ['protocol','seed','support_size']:
            assert r[field] == case[field]
        key = (r['case_id'], r['arm'])
        assert key not in checked
        checked.add(key)
        initial = case['initial']
        pool_ids = set(frame.iloc[case['pool']].compound_id)
        selected_ids = [s['compound_id'] for s in r['selections']]
        assert len(selected_ids) == len(set(selected_ids)) == 40
        assert set(selected_ids) <= pool_ids
        assert r['audit_ids'] == frame.iloc[case['audit']].compound_id.tolist()
        assert not set(selected_ids) & set(r['audit_ids'])
        cutoff = frame.iloc[case['pool']].value.quantile(.9)
        by_id = frame.set_index('compound_id')
        selected = by_id.loc[selected_ids]
        assert r['history'][-1]['top_decile_found'] == int((selected.value >= cutoff).sum())
        assert r['history'][-1]['additional_hits'] == int((selected.value >= 7).sum())
        actual = frame.iloc[case['audit']].value.to_numpy()
        for round_i,(h,p) in enumerate(zip(r['history'],r['audit_predictions'])):
            assert h['training_size'] == len(initial)+8*round_i
            assert np.isfinite(p).all()
            assert np.isclose(h['audit_mae'], np.abs(np.asarray(p)-actual).mean())
        assert len(r['history']) == len(r['audit_predictions']) == 6
        assert len(r['prediction_checks']) == 11
        if r['arm'] == 'chemeleon_tuned':
            for i,d in enumerate(r['training_diagnostics']):
                observed_ids = frame.iloc[initial].compound_id.tolist() + selected_ids[:8*i]
                observed_y = by_id.loc[observed_ids].value
                assert d['n_observed'] == len(initial)+8*i
                assert d['epochs'] == len(d['normalized_training_mse']) == 5
                assert np.isclose(d['target_mean'], observed_y.mean())
                assert d['encoder_weight_l2_change'] > 0
    if 'case_ids' in contract['inputs']:
        expected_pairs = {(c,a) for c in contract['inputs']['case_ids'] for a in contract['inputs']['arms']}
        assert checked == expected_pairs, 'Missing or unexpected case/arm pairs'
    write_json(root/'validation.json', {'valid':True,'replays_checked':len(records),
                                      'plan_sha256':digest(prepared/'plan.json'),
                                      'artifact_sha256':{p.name:digest(p) for p in paths},
                                      'checks':['matched plan indices','40 unique pool-only picks','audit separation',
                                                'round budgets','top-decile and hit counts','audit error recalculation',
                                                'finite predictions','where applicable: tuned observed-only normalization and encoder updates']})


def build():
    dev = Path('artifacts/stability-v1')
    frozen = Path('artifacts/transfer-v1')
    tuned = Path('artifacts/transfer-tuned-v1')
    validate(dev, Path('artifacts/broader-v2-prepared'), 108)
    validate(frozen, Path('artifacts/transfer-v1-prepared'), 96)
    validate(tuned, Path('artifacts/transfer-v1-prepared'), 6)
    heads = pd.read_csv(dev/'head_summary.csv')
    f,t = pd.read_csv(frozen/'metrics.csv'),pd.read_csv(tuned/'metrics.csv')
    matched = pd.concat([f[f.case_id.isin(t.case_id)],t],ignore_index=True)
    assert len(matched)==30
    matched.to_csv(tuned/'matched_metrics.csv',index=False)
    comparisons = []
    for cohort,frame,challenger in [('new_targets',f,'chemeleon_frozen'),('fine_tuning_pilot',matched,'chemeleon_tuned')]:
        pivot=frame.pivot(index=['task','case_id'],columns='arm',values='top_decile_found')
        for reference in [a for a in pivot.columns if a!=challenger]:
            delta=pivot[challenger]-pivot[reference]
            comparisons.append({'cohort':cohort,'challenger':challenger,'reference':reference,
                                'paired_cases':len(delta),'mean_delta':float(delta.mean()),
                                'wins':int((delta>0).sum()),'ties':int((delta==0).sum()),'losses':int((delta<0).sum())})
    contrasts=pd.DataFrame(comparisons)
    contrasts.to_csv(tuned/'paired_comparisons.csv',index=False)
    summary = f.groupby('arm')[['top_decile_found','final_mae','outside_guard']].mean().reset_index()
    by_task = f.groupby(['task','protocol','arm'])[['top_decile_found','final_mae']].mean().reset_index()
    by_task.to_csv(frozen/'target_protocol_summary.csv',index=False)
    pilot=matched.groupby('arm')[['top_decile_found','final_mae','outside_guard']].mean().reset_index()
    pilot_cases=matched.pivot(index=['task','protocol'],columns='arm',values='top_decile_found').reset_index()
    text='''# Aster: head stability and additional-target transfer

Completed 2026-10-13. The head decision used development only; the new-target
results below did not select or change the recipe. All 108 development, 96
additional-target, and six fine-tuned replays passed artifact validation.

## Development decision

Zero prediction clipping. The predeclared winner is `filter_10`: drop features
with observed standard deviation below 0.01, standardize retained features,
then ridge alpha 10. Refit transformations only on measurements revealed so far.
`mae` averages every audit round, `worst_mae` is the worst case/round, and
`outliers` counts prediction events outside the engineering guard [0,14].
Only the six CheMeleon candidate rows compete for recipe selection.

'''+table(heads)+'''

Centering stabilized predictions but failed the discovery-preservation gate.
Increasing regularization alone did not fix the pathology. Both feature filtering
and a variance floor passed; filtering won by the predeclared discovery criterion.
These are development results, not independent performance evidence.

## Frozen recipe on three additional targets

24 matched cases per arm: three targets, two protocols, two support sizes, two seeds.
Each case purchases 40 measurements. Scores are counts of strongest-decile pool
compounds found; higher is better. Final audit MAE is in pKi units; lower is better.
`outside_guard` counts audit and pool prediction events across the entire replay;
zero means none were flagged, not calibrated uncertainty or guaranteed reliability.

'''+table(summary)+'''

'''+table(by_task)+'''

The stable frozen features did not beat either Morgan model in the aggregate.
Morgan + ridge remains the strongest provisional reference for this experiment.
The table exposes target/protocol differences; the aggregate is not a universal
model ranking. Pool sizes, available top-decile counts and chemistry differ by case.

## Frozen versus adapted encoder: matched local CPU pilot

Six matched cases only: 32 starting measurements, seed 0, both protocols, all three
additional targets, and the same five eight-compound rounds. The table includes
only these same cases for every comparator. Encoder adaptation uses five fixed
epochs per round, observed-only normalized targets, and the same final ridge recipe.

'''+table(pilot)+'''\n\n'''+table(pilot_cases)+'''\n\n'''+table(contrasts)+'''

This is one small adaptation recipe and one acquisition seed per target/protocol.
A positive or negative result does not establish the best possible fine-tuning
method. The networks restart from the foundation checkpoint each round; the
auxiliary training head is replaced by ridge on the adapted features. This measures
this specific representation-adaptation intervention under a matched assay budget.

## Provenance and limitations

- Data: revision-pinned MoleculeACE Ki benchmarks; source/checkpoint hashes,
  identities, source exclusions and exact partitions are stored in the prepared plan.
- CHEMBL214 is serotonin 1A receptor, CHEMBL262 is GSK-3β, CHEMBL4203 is CLK4.
  Two are kinases; these are not three unrelated biological families.
- All previously inspected target identities were excluded from these tasks.
  1, 123 and 148 compounds respectively were removed for exposed-task overlap.
- Project-held-out targets are not guaranteed unseen by CheMeleon pretraining or
  publication-time model selection. Pretraining overlap remains unresolved.
- No target-wise significance claim: three tasks and correlated replay cases are
  too little evidence for a universal winner. No prospective laboratory test yet.
- Numerical guards expose gross extrapolation; they are not calibrated intervals.
  Even reasonable-valued predictions can select poorly under scaffold transfer.
- Replay timings exclude frozen embedding-cache preparation and should not be
  read as an end-to-end speed benchmark. Fine-tuning records include its encoder work.
- No cloud GPU or paid compute was provisioned. All computation used the local CPU.

See `docs/STABILITY_PROTOCOL.md` for settings, gates, method sources and reproduction.
Raw per-round predictions/selections, training diagnostics, paired comparisons,
validation results, contracts, source snapshots and dependency versions are preserved.
'''
    text += '\n![Matched discovery comparisons](comparison.png)\n'
    (tuned/'REPORT.md').write_text(text)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, frame, title in [(axes[0], summary, 'Additional targets: 24 cases / arm'),
                              (axes[1], pilot, 'Adaptation pilot: 6 matched cases / arm')]:
        labels = frame.arm.str.replace('chemeleon_', 'CheMeleon ').str.replace('morgan_', 'Morgan ')
        ax.barh(labels, frame.top_decile_found, color=['#5c71a6' if 'chemeleon' in a else '#4a897c' for a in frame.arm])
        ax.set(xlim=(0, 40), xlabel='Strongest-decile compounds found / 40 picks', title=title)
        for i, val in enumerate(frame.top_decile_found):
            ax.text(val + .3, i, f'{val:.2f}', va='center', fontsize=9)
    fig.savefig(tuned/'comparison.png', dpi=160)
    plt.close(fig)
    print(pilot.to_string(index=False))
    print(contrasts.to_string(index=False))


if __name__=='__main__':
    build()
