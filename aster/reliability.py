"""Predeclared policy comparisons and empirical reliability diagnostics."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from threadpoolctl import threadpool_limits
from .acquisition import ReliabilityModel, nearest_measured, select_batch, tanimoto
from .data import digest, fingerprints, write_json
from .experiment import LabelOracle
from .steady import seal


def correlation(a, b):
    return float(spearmanr(a,b).statistic) if np.std(a)>0 and np.std(b)>0 else None


def auc(truth, score):
    return float(roc_auc_score(truth, score)) if len(np.unique(truth))==2 else None


def simulate(x, audit_x, oracle, initial, settings, seed, policy):
    """No audit or unrevealed outcomes are arguments to the learning routine."""
    observed=np.asarray(initial,dtype=int).copy()
    values=oracle.reveal(observed)
    remaining=np.setdiff1d(np.arange(len(x)),observed)
    rng=np.random.default_rng(np.random.SeedSequence([seed,1]))
    predictions, selections, checks=[],[],[]
    for round_i in range(settings['rounds']+1):
        model=ReliabilityModel(settings,seed,forest=policy['id']=='morgan_rf').fit(x[observed],values)
        mean,spread=model.predict(audit_x)
        nearest,novelty=nearest_measured(audit_x,x[observed])
        predictions.append({'round':round_i,'training_size':len(observed),'mean':mean.tolist(),
                            'spread':spread.tolist(),'novelty':novelty.tolist(),
                            'nearest_observed_index':observed[nearest].tolist(),'half_width':model.half_width})
        lo,hi=settings['prediction_guard']
        checks.append({'round':round_i,'scope':'audit','min':float(mean.min()),'max':float(mean.max()),
                       'outside':int(((mean<lo)|(mean>hi)).sum())})
        if round_i==settings['rounds']:
            break
        mean,spread=model.predict(x[remaining])
        nearest,novelty=nearest_measured(x[remaining],x[observed])
        checks.append({'round':round_i,'scope':'pool','min':float(mean.min()),'max':float(mean.max()),
                       'outside':int(((mean<lo)|(mean>hi)).sum())})
        selected,reasons=select_batch(remaining,mean,spread,x[remaining],settings['batch_size'],policy,rng)
        lookup={int(index):j for j,index in enumerate(remaining)}
        batch=[]
        for rank,(index,reason) in enumerate(zip(selected,reasons),1):
            j=lookup[int(index)]
            batch.append({'round':round_i+1,'rank':rank,'index':int(index),'prediction':float(mean[j]),
                          'spread':float(spread[j]),'novelty':float(novelty[j]),
                          'nearest_observed_index':int(observed[nearest[j]]),**reason})
        measured=oracle.reveal(selected)  # only AFTER all eight choices are fixed
        for record,value in zip(batch,measured):
            record['observed_pki']=float(value)
        selections.extend(batch)
        observed=np.concatenate([observed,selected])
        values=np.concatenate([values,measured])
        remaining=np.setdiff1d(remaining,selected)
    return {'predictions':predictions,'selections':selections,'prediction_checks':checks}


def score(frame, x, case, result, settings):
    # Evaluator: hidden outcomes are accessed only after simulate has returned.
    working=case['initial']+case['pool']
    actual=frame.iloc[case['audit']].value.to_numpy()
    cutoff=float(np.quantile(frame.iloc[case['pool']].value,.9))
    initial_scaffolds=set(frame.iloc[case['initial']].scaffold)
    for s in result['selections']:
        row=frame.iloc[working[s['index']]]
        s['compound_id']=row.compound_id
        s['nearest_observed_id']=frame.iloc[working[s['nearest_observed_index']]].compound_id
        s['top_decile']=bool(row.value>=cutoff)
        s['hit']=bool(row.value>=settings['hit_threshold_pki'])
        s['scaffold']=row.scaffold
    rounds=[]
    for p in result['predictions']:
        error=np.abs(np.asarray(p['mean'])-actual)
        large=error>settings['large_error_threshold_pki']
        selected=[s for s in result['selections'] if s['round']<=p['round']]
        groups={s['scaffold'] for s in selected}
        diverse=[]
        for round_i in range(1,p['round']+1):
            batch=[working[s['index']] for s in selected if s['round']==round_i]
            sim=tanimoto(x[batch],x[batch])
            diverse.extend((1-sim[np.triu_indices(len(batch),1)]).tolist())
        h={'round':p['round'],'training_size':p['training_size'],
           'top_decile_found':sum(s['top_decile'] for s in selected),
           'additional_hits':sum(s['hit'] for s in selected),
           'scaffolds_found':len(groups),'novel_scaffolds':len(groups-initial_scaffolds),
           'mean_batch_distance':float(np.mean(diverse)) if diverse else None,
           'audit_mae':float(error.mean()), 'audit_rmse':float(np.sqrt(np.mean(error**2))),
           'interval_coverage':float((error<=p['half_width']).mean()),'interval_width':2*p['half_width'],
           'large_error_rate':float(large.mean()),
           'spread_error_spearman':correlation(p['spread'],error),
           'novelty_error_spearman':correlation(p['novelty'],error),
           'spread_large_error_auc':auc(large,p['spread']),
           'novelty_large_error_auc':auc(large,p['novelty'])}
        rounds.append(h)
    result['history']=rounds
    result['audit_ids']=frame.iloc[case['audit']].compound_id.tolist()
    result['top_decile_threshold']=cutoff
    return result


def selected_cases(plan, study, role):
    targets=study['development_tasks'] if role=='development' else study['evaluation_targets']
    sizes=study['development_support_sizes'] if role=='development' else study['evaluation_support_sizes']
    cases=[c for c in plan['cases'] if c['task'] in targets and c['support_size'] in sizes and
           c['seed'] in study['seeds'] and c['protocol'] in study['protocols']]
    expected={(t,n,s,p) for t in targets for n in sizes for s in study['seeds'] for p in study['protocols']}
    actual={(c['task'],c['support_size'],c['seed'],c['protocol']) for c in cases}
    if actual!=expected or len(cases)!=len(expected):
        raise ValueError('Missing or duplicate predeclared cases')
    if role=='evaluation' and any(c['role']!='evaluation' for c in cases):
        raise ValueError('Exposed targets cannot be fresh evaluation')
    return cases


def run(study_path,prepared,out,role,frozen):
    study=json.loads(study_path.read_text())
    plan=json.loads((prepared/'plan.json').read_text())
    cases=selected_cases(plan,study,role)
    inputs={'study':digest(study_path),'plan':digest(prepared/'plan.json'),'role':role,
            'case_ids':[c['id'] for c in cases],'policies':[p['id'] for p in study['policies']]}
    if role=='evaluation':
        freeze=json.loads(frozen.read_text())
        if freeze['study_sha256']!=digest(study_path) or plan['config'].get('frozen_policy_sha256')!=digest(frozen):
            raise ValueError('Evaluation is not bound to this frozen study')
        inputs['frozen']=digest(frozen)
    seal(out,inputs)
    (out/'source').mkdir(exist_ok=True)
    for source in Path(__file__).parent.glob('*.py'):
        shutil.copyfile(source,out/'source'/source.name)
    (out/'cases').mkdir(exist_ok=True)
    for task in sorted({c['task'] for c in cases}):
        path=prepared/f'{task}.csv'
        if digest(path)!=plan['prepared_hashes'][task]:
            raise ValueError('Prepared data changed')
        frame=pd.read_csv(path)
        x=fingerprints(frame.smiles.tolist())
        for case in [c for c in cases if c['task']==task]:
            working=case['initial']+case['pool']
            for policy in study['policies']:
                path=out/'cases'/f"{case['id']}__{policy['id']}.json"
                if path.exists():
                    continue
                start=time.monotonic()
                result=simulate(x[working],x[case['audit']],LabelOracle(frame.iloc[working].value.to_numpy()),
                                np.arange(case['support_size']),study,case['seed'],policy)
                result=score(frame,x,case,result,study)
                result.update({k:case[k] for k in ['task','protocol','support_size','seed']})
                result.update(case_id=case['id'],policy=policy['id'],role=role,seconds=time.monotonic()-start)
                write_json(path.with_suffix('.tmp'),result)
                path.with_suffix('.tmp').replace(path)
                print(f"{case['id']} {policy['id']}: top={result['history'][-1]['top_decile_found']} seconds={result['seconds']:.1f}",flush=True)
    records=[json.loads(p.read_text()) for p in sorted((out/'cases').glob('*.json'))]
    expected={(c['id'],p['id']) for c in cases for p in study['policies']}
    if {(r['case_id'],r['policy']) for r in records}!=expected or len(records)!=len(expected):
        raise ValueError('Unexpected or missing result records')
    rows=[]
    for r in records:
        for h in r['history']:
            rows.append({k:r[k] for k in ['case_id','task','protocol','support_size','seed','policy']}|h|
                        {'outside_guard':sum(c['outside'] for c in r['prediction_checks']), 'seconds':r['seconds']})
    metrics=pd.DataFrame(rows)
    metrics.to_csv(out/'round_metrics.csv',index=False)
    final=metrics[metrics['round']==study['rounds']].copy()
    final.to_csv(out/'final_metrics.csv',index=False)
    summary=final.groupby('policy')[['top_decile_found','audit_mae','novel_scaffolds','mean_batch_distance','outside_guard']].mean()
    summary.to_csv(out/'summary.csv')
    write_json(out/'coverage.json',{'expected':len(expected),'completed':len(records),'complete':True})
    if role=='development':
        pivot=final.pivot(index=['task','case_id'],columns='policy',values='top_decile_found')
        candidates=[p['id'] for p in study['policies'] if p['id'] not in ['greedy','random','morgan_rf']]
        gate=study['promotion_gate']
        decisions=[]
        for policy in candidates:
            delta=pivot[policy]-pivot.greedy
            mean=float(delta.mean())
            worst=float(delta.groupby(level='task').mean().min())
            mae=float(summary.loc[policy,'audit_mae'])
            outside=int(final[final.policy==policy].outside_guard.sum())
            passed=mean>=gate['mean_top_decile_gain_min'] and worst>=gate['worst_target_mean_gain_min'] and mae<=gate['mean_final_audit_mae_max'] and outside<=gate['outside_guard_max']
            decisions.append({'policy':policy,'mean_gain':mean,'worst_target_gain':worst,'mae':mae,'outliers':outside,'passes':passed})
        passing=sorted([d for d in decisions if d['passes']],key=lambda d:(-d['mean_gain'],d['mae'],d['policy']))
        write_json(out/'frozen_policy.json',{'study_sha256':digest(study_path),'development_metrics_sha256':digest(out/'final_metrics.csv'),
                   'selected':passing[0]['policy'] if passing else 'greedy','decisions':decisions,
                   'all_policy_settings':study['policies'],'evaluation_targets':study['evaluation_targets'],
                   'status':'frozen_before_additional_target_download'})
        print('FROZEN:',passing[0]['policy'] if passing else 'greedy',flush=True)
    print(summary.to_string(),flush=True)


def prepare(study_path,config_path,prepared,frozen):
    from .benchmark import prepare as prepare_benchmark
    study=json.loads(study_path.read_text())
    freeze=json.loads(frozen.read_text())
    if freeze['study_sha256']!=digest(study_path):
        raise ValueError('Study changed after freeze')
    config=json.loads(config_path.read_text())
    config['frozen_policy_sha256']=digest(frozen)
    config_file=prepared.with_name(prepared.name+'-config.json')
    if config_file.exists() or prepared.exists():
        raise ValueError('Choose a new prepared artifact directory')
    write_json(config_file,config)
    prepare_benchmark(config_file,Path('data/moleculeace'),prepared)
    path=prepared/'plan.json'
    plan=json.loads(path.read_text())
    plan['selection_basis']=study['selection_basis']
    plan['exposed_targets']=[t['id'] for t in config['tasks'] if t['role']=='development']
    selected_cases(plan,study,'evaluation')
    write_json(path,plan)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['develop','prepare','evaluate'])
    parser.add_argument('--study',type=Path,default=Path('configs/reliability-v1.json'))
    parser.add_argument('--data-config',type=Path,default=Path('configs/reliability-data-v1.json'))
    parser.add_argument('--prepared',type=Path,default=Path('artifacts/reliability-v1-prepared'))
    parser.add_argument('--frozen',type=Path,default=Path('artifacts/reliability-dev-v1/frozen_policy.json'))
    parser.add_argument('--output',type=Path)
    a=parser.parse_args()
    with threadpool_limits(limits=2):
        if a.command=='prepare':
            prepare(a.study,a.data_config,a.prepared,a.frozen)
        elif a.command=='develop':
            study=json.loads(a.study.read_text())
            run(a.study,Path(study['development_prepared']),a.output or Path('artifacts/reliability-dev-v1'),'development',a.frozen)
        else:
            run(a.study,a.prepared,a.output or Path('artifacts/reliability-v1'),'evaluation',a.frozen)


if __name__=='__main__':
    main()
