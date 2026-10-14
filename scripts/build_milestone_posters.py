"""Render exact, reproducible research posters from saved experiment metrics."""
from pathlib import Path
import hashlib
from decimal import Decimal, ROUND_HALF_UP
import html
import json
import textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/posters'
OUT.mkdir(parents=True,exist_ok=True)
BG='#F6F3EA'; INK='#143D3C'; TEAL='#237A71'; BLUE='#536CAA'; MUTED='#60706B'; ORANGE='#B56D3F'; GRAY='#A8B2AC'
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none'})
SOURCES=[
 ('ASAP–Polaris–OpenADMET dataset','https://doi.org/10.5281/zenodo.15582067','Experimental potency source for milestone 1.'),
 ('RDKit','https://www.rdkit.org/docs/GettingStartedInPython.html','Structure parsing, Morgan fingerprints and scaffold identities; reused throughout.'),
 ('scikit-learn','https://scikit-learn.org/stable/','Random forests, ridge regression, preprocessing, CV and evaluation metrics.'),
 ('MoleculeACE: paper and benchmark','https://doi.org/10.1021/acs.jcim.2c01073','van Tilborg et al.: activity-cliff benchmark; source data for milestones 2–4.'),
 ('MoleculeACE source revision','https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26/MoleculeACE/Data/benchmark_data','Exact pinned data revision; Aster uses its own acquisition protocol.'),
 ('CheMeleon research paper','https://arxiv.org/abs/2506.15792','Burns et al., Deep Learning Foundation Models from Classical Molecular Descriptors.'),
 ('CheMeleon checkpoint','https://zenodo.org/records/15460715','Frozen pretrained encoder for milestones 2–3; checksum verified.'),
 ('Chemprop foundation-model API','https://chemprop.readthedocs.io/en/main/chemeleon_foundation_finetuning.html','BondMessagePassing and MeanAggregation; custom observed-only adaptation in milestone 3.'),
 ('Efron: Bootstrap Methods (1979)','https://doi.org/10.1214/aos/1176344552','Bootstrap resampling foundation; not a confidence guarantee for Aster disagreement.'),
 ('Cross-validated predictions','https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.cross_val_predict.html','Background for training-only out-of-fold residual diagnostics in milestone 4.'),
 ('PyTorch','https://pytorch.org/docs/stable/index.html','Tensor execution and observed-only encoder optimization in milestones 2–3.'),
]
INPUTS=['artifacts/baseline/summary.json','artifacts/broader-v2/final_metrics.csv',
 'artifacts/stability-v1/head_summary.csv','artifacts/transfer-v1/metrics.csv',
 'artifacts/transfer-tuned-v1/matched_metrics.csv','artifacts/reliability-v1/final_metrics.csv',
 'artifacts/reliability-v1/reliability_summary.csv','artifacts/reliability-v1/decision.json']
baseline=json.loads((ROOT/INPUTS[0]).read_text())
broad=pd.read_csv(ROOT/INPUTS[1]); broad=broad[broad.role=='evaluation'].groupby('arm').mean(numeric_only=True)
heads=pd.read_csv(ROOT/INPUTS[2]).set_index('arm')
transfer=pd.read_csv(ROOT/INPUTS[3]).groupby('arm').mean(numeric_only=True)
pilot=pd.read_csv(ROOT/INPUTS[4]).groupby('arm').mean(numeric_only=True)
selection=pd.read_csv(ROOT/INPUTS[5]).groupby('policy').mean(numeric_only=True)
reliability=pd.read_csv(ROOT/INPUTS[6]).set_index('policy')
decision=json.loads((ROOT/INPUTS[7]).read_text())
assert decision['policy']=='explore' and not decision['passes_fresh_gate']
POSTERS=[dict(
 slug='01-baseline',number='01',title='Can a simple model choose\nbetter experiments?',
 deck='Aster begins with a real-data replay: predict activity, choose eight compounds, reveal their outcomes, and learn again.',
 stats=[(f"{baseline['greedy_mean_hits']:.0f} / 40",'HITS FOUND BY THE MODEL'),(f"{baseline['random_mean_hits']:.1f} / 40",'HITS FOUND AT RANDOM'),('10','MATCHED STARTING SEEDS')],
 chart_title='SARS-CoV-2 Mpro · discovery after 40 additional picks',
 labels=['Morgan + random forest','Random selection'],values=[baseline['greedy_mean_hits'],baseline['random_mean_hits']],colors=[TEAL,GRAY],
 axis='Additional assay hits per 40 picks · pIC50 ≥ 6',
 steps=[('01 / CURATE','Real potency data','1,328 rows → 922 eligible compounds; preserve the published train/test split.'),
        ('02 / ENCODE','Morgan fingerprints','2,048 structural bits; radius 2; retain stereochemistry.'),
        ('03 / PREDICT','Random forest','200 trees fit only the measurements revealed so far.'),
        ('04 / REPEAT','Select → reveal → refit','100 initial results; five batches of eight; compare with random picks.')],
 evaluation='712 compounds for training/acquisition; 210 held out for audit. Ten paired seeds, the same 40-pick budget, and hidden-label checks. This is a retrospective single-target experiment.',
 takeaway='The baseline chose many more assay hits than random. Random had slightly lower audit error (0.748 vs 0.793): prediction accuracy and useful selection are different objectives.',
 sources=['[1] ASAP–Polaris–OpenADMET · DOI 10.5281/zenodo.15582067','[2–3] RDKit + scikit-learn · Morgan fingerprints and random forests'],
 note='ASSAY HIT ≠ A SAFE OR EFFECTIVE DRUG',report='artifacts/baseline/REPORT.md'),
 dict(slug='02-broader-evaluation',number='02',title='The harder test:\ndoes deep learning help?',
 deck='Challenge the baseline with less starting data, unfamiliar chemical scaffolds, and frozen CheMeleon representations.',
 stats=[('144','COMPLETED REPLAYS'),('32 / 64','STARTING MEASUREMENTS'),(f"{broad.loc['morgan_ridge','top_decile_found']:.2f}",'BEST MEAN DISCOVERY COUNT')],
 chart_title='Two evaluation targets · mean discovery after 40 picks',
 labels=['Morgan + ridge','Frozen CheMeleon + ridge','Morgan + random forest','Random selection'],
 values=[broad.loc[k,'top_decile_found'] for k in ['morgan_ridge','chemeleon_ridge','morgan_rf','random']],colors=[TEAL,BLUE,MUTED,GRAY],
 axis='Compounds found from the pool’s strongest 10% / 40 picks',
 steps=[('01 / SPLIT','Development vs evaluation','One development target; two evaluation targets. Freeze rules first.'),
        ('02 / COMPARE','Two feature systems','Morgan bits versus 2,048 frozen CheMeleon features.'),
        ('03 / STRESS','Scaffold transfer','Separate starting chemistry, acquisition pool and audit scaffolds.'),
        ('04 / SCORE','Discovery + error','Three seeds; two starting sizes; five batches of eight.')],
 evaluation='Three tasks × two protocols × two starting sizes × three seeds × four arms = 144 replays. Chart uses androgen/glucocorticoid receptor tasks only; they share 133 molecular identities.',
 takeaway=f"No clear overall neural advantage. CheMeleon also had severe prediction failures: mean final audit MAE {broad.loc['chemeleon_ridge','audit_mae']:.2f}. Investigate the head before adding complexity.",
 sources=['[4–5] MoleculeACE · activity-cliff paper, DOI 10.1021/acs.jcim.2c01073','[6–8] CheMeleon · arXiv:2506.15792 · checkpoint + Chemprop','[2–3] RDKit + scikit-learn · Aster replay protocol, not an official leaderboard'],
 note='PRETRAINING OVERLAP UNRESOLVED · NO UNIVERSAL WINNER',report='artifacts/broader-v2/REPORT.md'),
 dict(slug='03-stability-and-adaptation',number='03',title='Stable predictions.\nNo neural advantage yet.',
 deck='Repair the prediction head on development data, freeze it, then test additional targets and a matched fine-tuning pilot.',
 stats=[('0','REPAIRED-HEAD GUARD VIOLATIONS'),('210','VALIDATED MAIN REPLAYS'),('28','PASSING SOFTWARE TESTS')],
 chart_title='Three additional targets · frozen-recipe evaluation',
 labels=['Morgan + ridge','Morgan + random forest','Stable frozen CheMeleon','Random selection'],
 values=[transfer.loc[k,'top_decile_found'] for k in ['morgan_ridge','morgan_rf','chemeleon_frozen','random']],colors=[TEAL,MUTED,BLUE,GRAY],
 axis='Compounds found from the pool’s strongest 10% / 40 picks',
 steps=[('01 / ABLATE','Six head recipes','Compare centering, a variance floor, feature filtering and ridge strength.'),
        ('02 / FREEZE','Filter + ridge','Drop observed feature SD <0.01; scale retained features; ridge α=10.'),
        ('03 / TRANSFER','New targets','Serotonin 1A, GSK-3β and CLK4; remove exposed-target overlaps.'),
        ('04 / ADAPT','A bounded neural pilot','Five epochs per round on observed labels; refit the same ridge policy.')],
 evaluation='108 development +96 fresh-target +6 tuned replays. Same starting measurements and 40-pick budgets within each comparison. Filters fit observed data only; no prediction clipping.',
 takeaway=f"Matched six-case pilot: frozen {pilot.loc['chemeleon_frozen','top_decile_found']:.2f} → tuned {pilot.loc['chemeleon_tuned','top_decile_found']:.2f} discoveries. Four ties, two losses. Keep Morgan/ridge provisional; this specific adaptation recipe did not help.",
 sources=['[4–5] MoleculeACE · fixed Ki tasks and scaffold tests','[6–8,11] CheMeleon + Chemprop + PyTorch · pretrained encoder and custom adaptation','[2–3] RDKit + scikit-learn · training-only transforms and ridge regression'],
 note='STABILITY FIXED IN THESE TESTS · FINE-TUNING RESULT IS A SMALL PILOT',report='artifacts/transfer-tuned-v1/REPORT.md'),
 dict(slug='04-reliability-and-selection',number='04',title='Which uncertainty signals\nactually help us choose?',
 deck='Test disagreement, chemical novelty and batch diversity while keeping the same molecules, starting data and measurement budget.',
 stats=[('252','VALIDATED REPLAYS'),('34','PASSING SOFTWARE TESTS'),('GREEDY','RETAINED PROVISIONAL DEFAULT')],
 chart_title='Three fresh targets · frozen primary policy and controls',
 labels=['Greedy Morgan + ridge','Exploration · primary test','Diversity · secondary','Explore + diversity · secondary','Cautious · secondary','Morgan + random forest','Random selection'],
 values=[selection.loc[k,'top_decile_found'] for k in ['greedy','explore','diverse','explore_diverse','cautious','morgan_rf','random']],
 colors=[TEAL,ORANGE,BLUE,BLUE,MUTED,MUTED,GRAY],axis='Compounds found from the pool’s strongest 10% / 40 picks',
 steps=[('01 / PREDICT','Keep the reference','Morgan + ridge α=10; no neural tuning in this milestone.'),
        ('02 / DIAGNOSE','Disagreement + novelty','16 bootstrap fits; nearest measured Tanimoto neighbor; CV residual bands.'),
        ('03 / SELECT','Seven fixed policies','Greedy, explore, cautious, diverse, hybrid, forest and random.'),
        ('04 / AUDIT','Freeze → transfer','84 development and 168 fresh-target replays; inspect exact score traces.')],
 evaluation=f"Under greedy: disagreement error-AUC {reliability.loc['greedy','spread_large_error_auc']:.3f}; novelty AUC {reliability.loc['greedy','novelty_large_error_auc']:.3f} (chance =0.5). Nominal-80% bands covered {100*reliability.loc['greedy','interval_coverage']:.1f}%; sigma scaffold cases only 63.4%.",
 takeaway=f"Exploration {selection.loc['explore','top_decile_found']:.2f} vs greedy {selection.loc['greedy','top_decile_found']:.2f}: no improvement. Diversity gained +0.83, below the +1 threshold. Novelty is a weak diagnostic; disagreement is not calibrated confidence.",
 sources=['[4–5] MoleculeACE · dopamine transporter, sigma receptor 1 and PI3Kα tasks','[9] Efron (1979) · bootstrap resampling · DOI 10.1214/aos/1176344552','[2–3,10] RDKit + scikit-learn · Tanimoto, ridge, CV and audit metrics'],
 note='SECONDARY DIVERSITY SIGNAL IS EXPLORATORY · NO PAID COMPUTE',report='artifacts/reliability-v1/REPORT.md')]


def block(fig,x,y,text,width,size=11,color=INK,**kwargs):
    lines='\n'.join(textwrap.fill(line,width=width,break_long_words=False,break_on_hyphens=False) for line in text.split('\n'))
    return fig.text(x,y,lines,fontsize=size,color=color,va='top',linespacing=1.42,**kwargs)


def box(fig,x,y,w,h,face='#ECEFE6'):
    fig.add_artist(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.008,rounding_size=0.008',transform=fig.transFigure,
                                 linewidth=.6,edgecolor='#D7DDD2',facecolor=face,zorder=-1))


def render(p):
    fig=plt.figure(figsize=(12,16),facecolor=BG)
    fig.text(.065,.957,'ASTER  /  RESEARCH NOTES',fontsize=12,fontweight='bold',color=INK)
    fig.text(.935,.957,f"MILESTONE {p['number']}",fontsize=11,color=TEAL,ha='right')
    fig.text(.065,.915,p['title'],fontsize=33,fontweight='bold',color=INK,va='top',linespacing=1.1,fontfamily='DejaVu Serif')
    block(fig,.065,.802,p['deck'],100,size=12.3,color=MUTED)
    for x,(value,label) in zip([.065,.36,.655],p['stats']):
        fig.text(x,.735,value,fontsize=27 if len(value)<7 else 24,fontweight='bold',color=TEAL)
        fig.text(x,.708,label,fontsize=9.5,color=MUTED)
    fig.text(.065,.665,p['chart_title'],fontsize=13,fontweight='bold',color=INK)
    ax=fig.add_axes([.295,.463,.635,.174],facecolor=BG)
    bars=ax.barh(np.arange(len(p['labels'])),p['values'],color=p['colors'],height=.62)
    ax.set_yticks(np.arange(len(p['labels'])),p['labels'],fontsize=10.5,color=INK)
    ax.invert_yaxis();ax.set_xlim(0,40);ax.set_xticks([0,10,20,30,40]);ax.tick_params(axis='both',length=0,labelcolor=MUTED,labelsize=10)
    ax.grid(axis='x',color='#DCE0D7',linewidth=.6);ax.set_axisbelow(True)
    for spine in ax.spines.values():spine.set_visible(False)
    ax.set_xlabel(p['axis'],fontsize=10,color=MUTED,labelpad=10)
    for bar,val in zip(bars,p['values']):
        ax.text(val+.45,bar.get_y()+bar.get_height()/2,str(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if p['number']!='01' else f'{val:g}',va='center',fontsize=11,fontweight='bold',color=INK)
    fig.text(.065,.404,'APPROACH  /  THE LEARNING LOOP',fontsize=11,fontweight='bold',color=TEAL)
    for i,(tag,title,body) in enumerate(p['steps']):
        x=.065+i*.224
        box(fig,x,.281,.201,.103)
        fig.text(x+.008,.369,tag,fontsize=8.8,color=TEAL,fontweight='bold')
        fig.text(x+.008,.347,title,fontsize=10.1,fontweight='bold',color=INK)
        block(fig,x+.008,.328,body,27,size=9.6)
        if i<3:
            fig.add_artist(FancyArrowPatch((x+.204,.332),(x+.219,.332),transform=fig.transFigure,arrowstyle='-|>',mutation_scale=9,color=TEAL))
    for x,title,body in [(.065,'EVALUATION',p['evaluation']),(.515,'WHAT WE LEARNED',p['takeaway'])]:
        box(fig,x,.135,.419,.119,face='#F0EEE4')
        fig.text(x+.01,.237,title,fontsize=10.5,color=TEAL,fontweight='bold')
        block(fig,x+.01,.217,body,55,size=10.6)
    fig.text(.065,.112,'METHODS, RESEARCH & OPEN SOURCE',fontsize=9.5,fontweight='bold',color=TEAL)
    for i,source in enumerate(p['sources']):
        fig.text(.065,.092-i*.014,source,fontsize=9.1,color=MUTED)
    fig.text(.065,.035,'Numbered references and source links: SOURCES.md · Full methods and limitations in the linked report.',fontsize=8.5,color=MUTED)
    fig.text(.065,.019,p['note'],fontsize=8.5,fontweight='bold',color=TEAL)
    fig.text(.935,.019,'ASTER / PUBLIC-DATA RESEARCH',fontsize=8,color=MUTED,ha='right')
    fig.savefig(OUT/f"{p['slug']}.png",dpi=200,facecolor=BG)
    fig.savefig(OUT/f"{p['slug']}.svg",facecolor=BG)
    plt.close(fig)


for poster in POSTERS:render(poster)
manifest={'posters':POSTERS,'sources':SOURCES,'input_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in INPUTS},
          'rendering':'Matplotlib Agg; exact data charts; editable text in SVG; 2400×3200 PNG',
          'illustration':'Separate built-in image generation; see approach-image-prompt.txt; conceptual diagram, not raw data.'}
if (OUT/'latest-approach.png').exists():
    manifest['illustration_sha256']=hashlib.sha256((OUT/'latest-approach.png').read_bytes()).hexdigest()
    manifest['illustration_generation']='Built-in image_gen; initial generation followed by one targeted scientific-label correction.'
    manifest['prompt_files']=['approach-image-prompt.txt','approach-image-edit-prompt.txt']
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
refs='# Aster poster sources and interpretation\n\n'
for i,(name,url,why) in enumerate(SOURCES,1):refs+=f'{i}. [{name}]({url}) — {why}\n\n'
refs+='''The posters use Aster's actual saved metrics. They do not copy third-party figures.
MoleculeACE and CheMeleon benchmark/publication results are distinct from Aster's
retrospective acquisition experiments. No unseen-pretraining or clinical claim is made.

Milestone 1 counts threshold assay hits; milestones 2–4 count strongest-decile
pool discoveries. Their numbers are **not directly comparable across milestones**.
The milestone 3 fine-tuning comparison uses six matched cases, separate from its
24-case frozen-transfer comparison. Replays are correlated; no target-level
significance claim is implied by the bar charts.

The current default remains greedy Morgan + ridge. The latest milestone tested
reliability-aware selection, not neural tuning. The illustrated diagram is a
conceptual explanation; audited numeric evidence is in the experiment reports.
'''
(OUT/'SOURCES.md').write_text(refs)
cards=''
for p in POSTERS:
    title=p['title'].replace('\n',' ')
    cards+=f'''<article><h2>{p['number']} · {html.escape(title)}</h2><a href="{p['slug']}.png"><img src="{p['slug']}.png" alt="Milestone {p['number']} research poster: {html.escape(title)}"></a><p><a href="{p['slug']}.png" download>PNG · 2400×3200</a> <a href="{p['slug']}.svg" download>Scalable SVG</a> <a href="../../{p['report']}">Full report</a></p></article>'''
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aster research milestones</title><style>
body{margin:0;background:#f6f3ea;color:#143d3c;font:17px/1.5 system-ui,sans-serif}header,main,footer{max-width:1240px;margin:auto;padding:32px}h1{font:clamp(32px,5vw,60px)/1.1 Georgia,serif;margin:12px 0}h2{font-size:21px}p{max-width:850px}a{color:#237a71}nav{display:flex;gap:22px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:32px}article img{width:100%;border:1px solid #d7ddd2;border-radius:10px;box-shadow:0 10px 24px #143d3c12}article p{display:flex;gap:18px;font-size:14px}.diagram{margin-top:48px}.diagram img{width:100%;border-radius:10px}.eyebrow{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#60706b}.note{background:#ecefe6;padding:20px;border-radius:12px}@media(max-width:720px){.grid{grid-template-columns:1fr}header,main,footer{padding:20px}}@media print{header,footer,article h2,article p,.diagram{display:none}.grid{display:block}article{break-after:page}article img{border:0;box-shadow:none;width:100%;max-height:96vh;object-fit:contain}main{padding:0}@page{size:A3 portrait;margin:8mm}}
</style><header><div class="eyebrow">Aster / four completed scientific milestones</div><h1>From a baseline to better questions.</h1><p>A visual record of what we built, how we tested it, and what the evidence supports. These are retrospective public-data studies, not new laboratory discoveries.</p><nav><a href="SOURCES.md">Research & open-source references</a><a href="../../ROADMAP.md">Roadmap</a><a href="../../docs/RELIABILITY_RESULTS.md">Latest findings</a></nav><p class="note"><strong>Current position:</strong> first Phase 3 selection/reliability comparison complete. Greedy Morgan + ridge remains the provisional reference; a thin campaign workflow is next. Metrics differ across milestones—read each chart's definition.</p></header><main><div class="grid">'''+cards+'''</div><section class="diagram"><h2>The latest approach, illustrated</h2><p>Reliability-aware experiment selection; neural fine-tuning was the previous comparison. The main loop learns only from revealed measurements.</p><a href="latest-approach.png"><img src="latest-approach.png" alt="Aster current workflow: known measurements, Morgan fingerprints, ridge prediction, diagnostic signals, select eight, reveal existing outcomes and refit."></a><p><a href="latest-approach.png" download>Download workflow image</a> · <a href="approach-image-prompt.txt">Image-generation prompt</a> · <a href="approach-image-edit-prompt.txt">Correction prompt</a></p></section></main><footer>Poster charts rendered from saved metrics with Matplotlib. Illustration generated with the built-in image tool and checked for scientific consistency. Source hashes are recorded in manifest.json.</footer></html>'''
(OUT/'index.html').write_text(page)
print(f'Rendered {len(POSTERS)} posters with PNG/SVG exports and gallery at {OUT}')
