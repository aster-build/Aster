"""Additional-target evaluation, only after development recipe is frozen."""
import argparse
import json
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from .adaptation import AdaptedCheMeleon
from .data import digest, fingerprints, write_json
from .heads import make_head
from .representations import frozen_chemeleon
from .steady import reference_factory, run_case, seal, summarize



def validate_evaluation_plan(plan, freeze, study, frozen_sha):
    settings = plan['config']
    if settings.get('frozen_recipe_sha256') != frozen_sha:
        raise ValueError('Prepared evaluation is bound to a different frozen recipe')
    for field in ['rounds', 'batch_size']:
        if settings[field] != study[field]:
            raise ValueError('Evaluation measurement budget differs from predeclared study')
    expected = set(product(freeze['new_targets'], study['evaluation_protocols'],
                           study['evaluation_support_sizes'], study['evaluation_seeds']))
    cases = [c for c in plan['cases'] if c['role'] == 'evaluation']
    actual = {(c['task'], c['protocol'], c['support_size'], c['seed']) for c in cases}
    if actual != expected or len(cases) != len(expected):
        raise ValueError('Evaluation cases differ from the predeclared task/seed/support/protocol grid')


def evaluate(prepared, frozen, study_path, out, fine_tune=False, smoke=False):
    study = json.loads(study_path.read_text())
    freeze = json.loads(frozen.read_text())
    if freeze['selected'] is None or freeze['study_sha256'] != digest(study_path):
        raise ValueError('Missing or mismatched frozen recipe')
    plan_path = prepared / 'plan.json'
    plan = json.loads(plan_path.read_text())
    settings = plan['config']
    if not smoke:
        validate_evaluation_plan(plan, freeze, study, digest(frozen))
    cases = [c for c in plan['cases'] if c['role'] == ('development' if smoke else 'evaluation')]
    if smoke:
        cases = [c for c in cases if c['protocol'] == 'published' and c['support_size'] == 32 and c['seed'] == 0]
    else:
        if {c['task'] for c in cases} != set(freeze['new_targets']):
            raise ValueError('Evaluation target IDs differ from the predeclared targets')
        if any(c['task'] in ['CHEMBL1862_Ki', 'CHEMBL1871_Ki', 'CHEMBL2034_Ki'] for c in cases):
            raise ValueError('Previously inspected task used as fresh evaluation')
    tune = freeze['fine_tuning']
    if fine_tune or smoke:
        cases = [c for c in cases if c['support_size'] in tune['support_sizes'] and
                 c['seed'] in tune['seeds'] and c['protocol'] in tune['protocols']]
    arms = ['chemeleon_tuned'] if fine_tune or smoke else ['random', 'morgan_rf', 'morgan_ridge', 'chemeleon_frozen']
    seal(out, {'plan': digest(plan_path), 'frozen_recipe': digest(frozen), 'study': digest(study_path),
               'arms': arms, 'case_ids': [c['id'] for c in cases]})
    (out / 'cases').mkdir(exist_ok=True)
    for task in sorted({c['task'] for c in cases}):
        path = prepared / f'{task}.csv'
        if digest(path) != plan['prepared_hashes'][task]:
            raise ValueError('Prepared data changed')
        frame = pd.read_csv(path)
        structures = frame.smiles.to_numpy()
        fp = fingerprints(structures.tolist()) if not (fine_tune or smoke) else None
        embeddings = frozen_chemeleon(structures.tolist(), Path('data/models/chemeleon_mp.pt'),
                     settings['checkpoint_sha256'], Path('data/embeddings')) if not (fine_tune or smoke) else None
        for case in [c for c in cases if c['task'] == task]:
            for arm in arms:
                path = out / 'cases' / f"{case['id']}__{arm}.json"
                if path.exists():
                    continue
                if arm == 'chemeleon_tuned':
                    x = structures
                    factory = lambda seed: AdaptedCheMeleon(freeze['selected'], tune, 'data/models/chemeleon_mp.pt', settings['checkpoint_sha256'], seed)
                elif arm == 'chemeleon_frozen':
                    x = embeddings
                    factory = lambda seed: make_head(freeze['selected'])
                else:
                    x, factory = fp, reference_factory(arm, settings)
                result = run_case(frame, x, case, settings, arm, factory, study['gate']['prediction_guard'])
                write_json(path.with_suffix('.tmp'), result)
                path.with_suffix('.tmp').replace(path)
                print(f"{case['id']} {arm}: top={result['history'][-1]['top_decile_found']} MAE={result['history'][-1]['audit_mae']:.3f} seconds={result['seconds']:.1f}", flush=True)
    scores = summarize(out)
    write_json(out / 'coverage.json', {'expected': len(cases)*len(arms), 'completed': len(scores),
                                      'complete': len(scores) == len(cases)*len(arms)})
    print(scores.groupby('arm')[['top_decile_found', 'final_mae', 'outside_guard', 'seconds']].mean().to_string(), flush=True)



def prepare_transfer(config_path, frozen, study_path, prepared):
    from .benchmark import prepare
    study = json.loads(study_path.read_text())
    freeze = json.loads(frozen.read_text())
    if freeze['selected'] is None or freeze['study_sha256'] != digest(study_path):
        raise ValueError('A passing, matching development recipe must be frozen first')
    config = json.loads(config_path.read_text())
    config['frozen_recipe_sha256'] = digest(frozen)
    instantiated = prepared.with_name(prepared.name + '-config.json')
    if prepared.exists() or instantiated.exists():
        raise ValueError('Prepared artifacts already exist; choose a new path')
    instantiated.parent.mkdir(parents=True, exist_ok=True)
    write_json(instantiated, config)
    prepare(instantiated, Path('data/moleculeace'), prepared)
    plan_path = prepared / 'plan.json'
    plan = json.loads(plan_path.read_text())
    plan['selection_basis'] = config['selection_basis']
    plan['exposed_tasks'] = [t['id'] for t in config['tasks'] if t['role'] == 'development']
    validate_evaluation_plan(plan, freeze, study, digest(frozen))
    write_json(plan_path, plan)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prepared', type=Path, default=Path('artifacts/transfer-v1-prepared'))
    p.add_argument('--frozen', type=Path, default=Path('artifacts/stability-v1/frozen_recipe.json'))
    p.add_argument('--study', type=Path, default=Path('configs/stability-v1.json'))
    p.add_argument('--output', type=Path, default=Path('artifacts/transfer-v1'))
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--config', type=Path, default=Path('configs/transfer-v1.json'))
    p.add_argument('--fine-tune', action='store_true')
    p.add_argument('--smoke', action='store_true')
    a = p.parse_args()
    if a.prepare:
        prepare_transfer(a.config, a.frozen, a.study, a.prepared)
    else:
        evaluate(a.prepared, a.frozen, a.study, a.output, a.fine_tune, a.smoke)


if __name__ == '__main__':
    main()
