"""Validate acquisition traces and report the predeclared primary comparison."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .acquisition import tanimoto
from .data import digest, fingerprints, write_json
from .stability_report import table


def validate(root,prepared,study):
    plan=json.loads((prepared/'plan.json').read_text())
    contract=json.loads((root/'contract.json').read_text())
    assert contract['inputs']['plan']==digest(prepared/'plan.json')
    assert contract['inputs']['study']==digest(Path('configs/reliability-v1.json'))
    paths=sorted((root/'cases').glob('*.json'))
    records=[json.loads(p.read_text()) for p in paths]
    expected={(c,p) for c in contract['inputs']['case_ids'] for p in contract['inputs']['policies']}
    assert {(r['case_id'],r['policy']) for r in records}==expected and len(records)==len(expected)
    cases={c['id']:c for c in plan['cases']}
    policies={p['id']:p for p in study['policies']}
    frames={}
    fp={}
    for task in {r['task'] for r in records}:
        path=prepared/f'{task}.csv'
        assert digest(path)==plan['prepared_hashes'][task]
        frames[task]=pd.read_csv(path)
        fp[task]=fingerprints(frames[task].smiles.tolist())
    for r in records:
        c=cases[r['case_id']]; f=frames[r['task']]; x=fp[r['task']]
        assert all(r[k]==c[k] for k in ['task','protocol','support_size','seed'])
        working=c['initial']+c['pool']
        ids=[s['compound_id'] for s in r['selections']]
        assert len(ids)==len(set(ids))==study['rounds']*study['batch_size']
        assert set(ids)<=set(f.iloc[c['pool']].compound_id)
        assert r['audit_ids']==f.iloc[c['audit']].compound_id.tolist()
        assert not set(ids)&set(r['audit_ids'])
        cutoff=np.quantile(f.iloc[c['pool']].value,.9)
        assert np.isclose(cutoff,r['top_decile_threshold'])
        observed=list(range(c['support_size']))
        for round_i in range(1,study['rounds']+1):
            picks=[s for s in r['selections'] if s['round']==round_i]
            assert len(picks)==study['batch_size']
            prefix=[]
            for s in picks:
                idx=s['index']
                assert idx not in observed and idx not in prefix
                row=f.iloc[working[idx]]
                assert s['compound_id']==row.compound_id and s['observed_pki']==row.value
                assert s['top_decile']==bool(row.value>=cutoff)
                assert s['nearest_observed_index'] in observed
                similarity=tanimoto(x[working[idx]:working[idx]+1],x[np.asarray(working)[observed]])[0]
                assert np.isclose(s['novelty'],1-similarity.max())
                p=policies[r['policy']]
                if p['id']!='random':
                    assert np.isclose(s['uncertainty_term'],p['uncertainty_weight']*s['spread'])
                    redundancy=float(tanimoto(x[working[idx]:working[idx]+1],x[np.asarray(working)[prefix]]).max()) if prefix else 0.
                    assert np.isclose(s['diversity_penalty'],p['diversity_weight']*redundancy)
                    assert np.isclose(s['score'],s['prediction']+s['uncertainty_term']-s['diversity_penalty'])
                prefix.append(idx)
            observed.extend(prefix)
        actual=f.iloc[c['audit']].value.to_numpy()
        assert len(r['history'])==len(r['predictions'])==study['rounds']+1
        assert len(r['prediction_checks'])==2*study['rounds']+1
        for round_i,(h,p) in enumerate(zip(r['history'],r['predictions'])):
            mean=np.asarray(p['mean']);spread=np.asarray(p['spread'])
            assert len(mean)==len(actual) and np.isfinite(mean).all()
            assert np.isfinite(spread).all() and (spread>=0).all()
            assert h['training_size']==p['training_size']==c['support_size']+round_i*study['batch_size']
            observed_at_round=list(range(c['support_size']))+[s['index'] for s in r['selections'] if s['round']<=round_i]
            assert set(p['nearest_observed_index'])<=set(observed_at_round)
            assert np.isclose(h['audit_mae'],np.abs(mean-actual).mean())
            assert h['top_decile_found']==sum(s['top_decile'] for s in r['selections'] if s['round']<=round_i)
            assert np.isclose(h['interval_coverage'],(np.abs(mean-actual)<=p['half_width']).mean())
    write_json(root/'validation.json',{'valid':True,'replays_checked':len(records),
        'plan_sha256':digest(prepared/'plan.json'),'artifact_sha256':{p.name:digest(p) for p in paths},
        'checks':['complete case/policy coverage','unique pool-only batches','audit separation','observed-only nearest references',
                  'budget and training sizes','score and diversity decomposition','finite predictions','discovery counts','audit MAE and coverage']})


def build():
    study=json.loads(Path('configs/reliability-v1.json').read_text())
    dev=Path('artifacts/reliability-dev-v1'); out=Path('artifacts/reliability-v1')
    freeze=json.loads((dev/'frozen_policy.json').read_text())
    validate(dev,Path(study['development_prepared']),study)
    validate(out,Path('artifacts/reliability-v1-prepared'),study)
    final=pd.read_csv(out/'final_metrics.csv'); rounds=pd.read_csv(out/'round_metrics.csv')
    pivot=final.pivot(index=['task','case_id'],columns='policy',values='top_decile_found')
    contrasts=[]
    for p in [p['id'] for p in study['policies'] if p['id']!='greedy']:
        d=pivot[p]-pivot.greedy
        contrasts.append({'policy':p,'mean_gain_vs_greedy':float(d.mean()),'worst_target_mean_gain':float(d.groupby(level='task').mean().min()),
                          'wins':int((d>0).sum()),'ties':int((d==0).sum()),'losses':int((d<0).sum())})
    paired=pd.DataFrame(contrasts)
    paired.to_csv(out/'paired_comparisons.csv',index=False)
    summary=final.groupby('policy')[['top_decile_found','audit_mae','novel_scaffolds','mean_batch_distance','outside_guard']].mean().reset_index()
    target=final.groupby(['task','protocol','policy'])[['top_decile_found','audit_mae']].mean().reset_index()
    target.to_csv(out/'target_protocol_summary.csv',index=False)
    reliability_columns=['spread_error_spearman','novelty_error_spearman','spread_large_error_auc','novelty_large_error_auc','interval_coverage','interval_width']
    reliability=rounds.groupby('policy')[reliability_columns].mean().reset_index()
    reliability.to_csv(out/'reliability_summary.csv',index=False)
    bands=rounds.groupby(['task','protocol','policy'])[['interval_coverage','interval_width']].mean().reset_index()
    bands['nominal_coverage']=study['nominal_interval_coverage']
    bands['coverage_gap']=bands.interval_coverage-bands.nominal_coverage
    bands['within_predeclared_tolerance']=bands.coverage_gap.abs()<=study['reliability_gate']['interval_coverage_tolerance']
    bands.to_csv(out/'band_diagnostics.csv',index=False)
    rounds.groupby(['task','protocol','policy'])[reliability_columns].mean().to_csv(out/'reliability_by_target.csv')
    primary=freeze['selected']
    if primary=='greedy':
        primary_result={'policy':primary,'passes_fresh_gate':False,'reason':'No challenger passed development; primary remains greedy.'}
    else:
        row=paired.set_index('policy').loc[primary]
        score=summary.set_index('policy').loc[primary]
        gate=study['promotion_gate']
        passes=bool(row.mean_gain_vs_greedy>=gate['mean_top_decile_gain_min'] and row.worst_target_mean_gain>=gate['worst_target_mean_gain_min'] and
                    score.audit_mae<=gate['mean_final_audit_mae_max'] and score.outside_guard<=gate['outside_guard_max'])
        primary_result={'policy':primary,'passes_fresh_gate':passes,'mean_gain':float(row.mean_gain_vs_greedy),
                        'worst_target_mean_gain':float(row.worst_target_mean_gain),
                        'recommendation':'provisional candidate for further validation' if passes else 'retain greedy Morgan ridge as default'}
    write_json(out/'decision.json',primary_result)
    # Reliability screens are descriptive, not used to revise the frozen policy.
    screens=[]
    for cohort,root in [('development',dev),('evaluation',out)]:
        data=pd.read_csv(root/'round_metrics.csv')
        for policy in sorted({'greedy',primary}):
            m=data[data.policy==policy]
            for signal in ['spread','novelty']:
                a=float(m[f'{signal}_large_error_auc'].mean());rho=float(m[f'{signal}_error_spearman'].mean())
                screens.append({'cohort':cohort,'policy':policy,'signal':signal,'mean_auc':a,'mean_spearman':rho,
                                'passes_descriptive_screen':bool(a>=study['reliability_gate']['mean_large_error_auc_min'] and rho>=study['reliability_gate']['mean_error_spearman_min'])})
    pd.DataFrame(screens).to_csv(out/'reliability_screens.csv',index=False)
    # Export interpretable historical recommendations for inspection; not a new assay proposal.
    records=[json.loads(p.read_text()) for p in sorted((out/'cases').glob(f'*__{primary}.json'))]
    examples=[]
    for r in records:
        for s in r['selections']:
            examples.append({'task':r['task'],'case_id':r['case_id'],'policy':primary,**s})
    pd.DataFrame(examples).to_csv(out/'recommendation_trace.csv',index=False)
    body=f'''# Aster milestone 4: reliability-aware experimental selection

Completed retrospective study. **Frozen primary policy: {primary}.**
Fresh-target decision: {primary_result.get('recommendation',primary_result.get('reason'))}.

## Design

Development: three previously exposed targets, 32 starting measurements, two seeds,
two protocols, seven policies = 84 replays. Fresh evaluation: three additional
targets, 32/64 starting measurements, two seeds, two protocols, seven policies =
168 replays. Every case has five batches of eight; no hidden outcomes affect selection.
Both Morgan reference models and random selection are retained.

Morgan/ridge alpha 10 supplies the point prediction. Sixteen bootstrap ridge fits
supply a disagreement proxy; Morgan Tanimoto distance supplies chemical novelty.
The forest reference uses 200 trees and reports tree disagreement separately.
Exploration adds 0.5 times disagreement, caution subtracts 1.0 times disagreement,
and diversity subtracts 0.5 times maximum similarity to compounds already chosen
inside the same batch. No neural training was performed in this milestone.

All seven settings were predeclared. Only development picked the primary policy.
Its promotion gate requires at least +1 top-decile discovery on average, no target
mean loss worse than -1, final mean MAE <=1.25 and zero guard violations. Secondary
policies remain descriptive comparisons; do not select a new winner from this table
and claim independent validation.

## Development selection

'''+table(pd.DataFrame(freeze['decisions']))+'''

## Fresh targets: discovery and prediction

The endpoint is pKi. Discovery counts refer to the strongest 10% of each candidate
pool, not drug candidates proven safe or effective. Higher discovery is better;
lower MAE is better. Novel scaffold counts include inactive selected compounds.
Batch distance is mean pairwise 1-Tanimoto within each eight-compound batch.

'''+table(summary)+'''\n\n'''+table(paired)+'''\n\n'''+table(target)+'''

## Do the reliability signals actually identify errors?

All-round summaries weight case/rounds equally. Error AUC tests whether a signal
ranks absolute errors >1 pKi above smaller errors; 0.5 is chance ranking. Spearman
measures association with absolute error. These are descriptive summaries of
correlated replays, not independent replications or significance tests.

'''+table(reliability)+'''\n\n'''+table(pd.DataFrame(screens))+'''

The displayed 80% residual bands use only three-fold out-of-fold residuals on
currently observed training data. The point model then fits all observations.
These are approximate empirical bands, NOT guaranteed conformal intervals.
Adaptive measurement selection, small sample sizes, and scaffold shift can break
coverage. Report measured audit coverage and width; do not label raw bootstrap
spread as a calibrated confidence interval. The bands are diagnostic only and
never drive the acquisition score.

## Evaluation boundaries

- Fresh tasks: CHEMBL238_Ki (dopamine transporter), CHEMBL287_Ki (sigma receptor 1),
  CHEMBL4005_Ki (PI3K alpha). Target identities were fixed before development runs.
- Exclude molecular identities shared with all six previously inspected tasks.
  Exact exclusions and cross-target overlaps are in the prepared data audit/plan.
- Two protocols: published partitions and scaffold-disjoint initial support,
  candidate pool and audit partitions. New acquisitions gradually change the
  training domain. Retrospective selected pools are not arbitrary chemical space.
- Only three fresh targets and two seeds: no universal policy superiority claim.
  These results are now inspected and must not be reused as blind model selection.
- A positive reliability association does not prove that exploring uncertainty
  improves discovery. The experiment tests both questions separately.
- No paid compute, neural retraining, laboratory assays or production deployment.

## Artifacts and sources

252 replays validated for unique pool-only picks, observed-only nearest references,
score decompositions, budget accounting, prediction errors and interval coverage.
`recommendation_trace.csv` explains historical picks; it is not a prospective lab batch.
`decision.json` records the primary-policy decision; `reliability_screens.csv` records
predeclared descriptive screens. Contracts, source snapshots and exact data hashes
are preserved. See `docs/RELIABILITY_PROTOCOL.md` for commands and primary sources.
'''
    (out/'REPORT.md').write_text(body)
    print(json.dumps(primary_result,indent=2))
    print(summary.to_string(index=False))
    print(reliability.to_string(index=False))


if __name__=='__main__':
    build()
