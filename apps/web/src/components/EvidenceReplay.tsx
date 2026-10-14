'use client';
import {useEffect,useState} from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import {Wordmark} from './Logo';
import {api,type CampaignSummary} from '@/lib/campaign-api';
import {stages,type Replay,type StructureEvidence,type Contact} from '@/lib/replay';
import DockingPanel,{type DockPose} from './DockingPanel';
import './replay.css';

const MolecularScene=dynamic(()=>import('./MolecularScene'),{ssr:false,loading:()=> <div className="scene-status">Preparing molecular viewer…</div>});
const fmt=(v:number|null|undefined)=>v==null?'—':v.toFixed(2);

export default function EvidenceReplay(){
 const [evidence,setEvidence]=useState<StructureEvidence|null>(null);
 const [campaigns,setCampaigns]=useState<CampaignSummary[]>([]);
 const [replay,setReplay]=useState<Replay|null>(null);
 const [campaignId,setCampaignId]=useState('');
 const [roundIndex,setRoundIndex]=useState(0);const [stage,setStage]=useState(0);
 const [playing,setPlaying]=useState(false);const [speed,setSpeed]=useState(1);
 const [selected,setSelected]=useState('');
 const [directCompound,setDirectCompound]=useState<string|null>(null);
 const [view,setView]=useState<'protein'|'pocket'|'ligand'>('protein');
 const [contact,setContact]=useState<Contact|null>(null);
 const [tour,setTour]=useState(false);const [tourStep,setTourStep]=useState(0);
 const [error,setError]=useState('');const [loading,setLoading]=useState(false);
 const [pickNote,setPickNote]=useState('');
 const [dockPose,setDockPose]=useState<DockPose|null>(null);
 useEffect(()=>{if(dockPose){setView('pocket');setContact(null);setTour(false);}},[dockPose]);
 useEffect(()=>{
  let live=true;
  fetch('/structures/8y2g/manifest.json').then(r=>{if(!r.ok)throw Error('Structure metadata unavailable');return r.json();}).then(d=>{if(live)setEvidence(d);}).catch(e=>{if(live)setError(e.message);});
  api<CampaignSummary[]>('/campaigns').then(rows=>{if(!live)return;setCampaigns(rows);const saved=new URLSearchParams(location.search).get('campaign')||localStorage.getItem('aster-campaign');setCampaignId((rows.find(c=>c.id===saved&&c.rounds.length)||rows.find(c=>c.rounds.length)||rows[0])?.id||'');}).catch(e=>{if(live)setError(e.message);});
  return()=>{live=false;};
 },[]);
 useEffect(()=>{
  if(!campaignId)return;let live=true;setLoading(true);setError('');setPlaying(false);setReplay(null);setRoundIndex(0);setStage(0);setSelected('');setDirectCompound(null);
  api<Replay>(`/campaigns/${campaignId}/replay`).then(d=>{if(live){setReplay(d);const requested=new URLSearchParams(location.search).get('compound');if(requested){const index=d.rounds.findIndex(r=>r.scored.some(s=>s.compound_id===requested));if(index>=0){setRoundIndex(index);setStage(2);setSelected(requested);}else{setDirectCompound(requested);setStage(2);}}}}).catch(e=>{if(live)setError(e.message);}).finally(()=>{if(live)setLoading(false);});
  return()=>{live=false;};
 },[campaignId]);
 const round=replay?.rounds[roundIndex];
 const pick=round?.scored.find(r=>r.compound_id===selected)||round?.recommendations[0];
 const selectedRecommendation=round?.recommendations.find(r=>r.compound_id===pick?.compound_id);
 const result=pick?round?.results[pick.compound_id]:undefined;
 const priorScores=new Map((replay?.rounds[roundIndex-1]?.scored||[]).map(r=>[r.compound_id,r.prediction]));
 const steps=(replay?.rounds.length||0)*stages.length;
 const position=roundIndex*stages.length+stage;
 function seek(next:number){const bounded=Math.max(0,Math.min(steps-1,next));setRoundIndex(Math.floor(bounded/stages.length));setStage(bounded%stages.length);setSelected('');}
 useEffect(()=>{if(!playing||!steps)return;const id=setTimeout(()=>{if(position>=steps-1)setPlaying(false);else seek(position+1);},2400/speed);return()=>clearTimeout(id);},[playing,position,steps,speed]);
 useEffect(()=>{if(!tour||!evidence)return;const id=setTimeout(()=>{
  const next=tourStep+1;setTourStep(next);
  if(next===1){setView('pocket');setContact(null);}else if(next===2){setView('ligand');setContact(null);}else if(next===3){setContact(evidence.contacts[0]);}else setTour(false);
 },2300);return()=>clearTimeout(id);},[tour,tourStep,evidence]);
 function camera(v:typeof view){setTour(false);setContact(null);setView(v);}
 function chooseContact(c:Contact){setTour(false);setContact(c);setPickNote('');}
 const values=round?.recommendations.flatMap(r=>{const o=round.results[r.compound_id];return o?.value!=null?[{...r,observed:o.value}]:[]})||[];
 const mae=values.length?values.reduce((s,r)=>s+Math.abs(r.prediction-r.observed),0)/values.length:null;
 const stageText=round?[
  `${round.training.length} measurements were available before round ${round.round}. Future outcomes are absent from this training snapshot.`,
  `The saved ${round.recipe.model} fit uses ${round.model.feature_count.toLocaleString()} fingerprint features, radius ${round.recipe.radius}, and ridge α = ${round.recipe.alpha}. This is a replay of the fit, not live retraining.`,
  `${round.scored.length} saved predictions are available (${round.score_coverage}). Higher predicted ${replay?.endpoint} ranks first among eligible, unlocked candidates.`,
  `${round.recommendations.length} compounds were committed after applying locks and exclusions. This replay cannot change the saved decision.`,
  `${Object.keys(round.results).length} of ${round.recommendations.length} outcomes are recorded. ${round.status==='complete'?'The next recorded round uses the expanded measurement set.':'Missing or failed outcomes remain explicit.'}`
 ][stage]:'';
 return <div className="evidence-page">
  <header className="evidence-nav"><Link href="/"><Wordmark/></Link><span>/ Molecular evidence</span><Link className="back-dashboard" href="/dashboard">Campaign dashboard ↗</Link></header>
  <div className="replay-heading"><div><p className="replay-eyebrow">ASTER · STRUCTURE & DECISION REPLAY</p><h1>See the evidence. Follow the decision.</h1><p>Explore an experimental complex alongside the measurements that guide each batch.</p></div><span className="reference-tag">Recorded decisions · exploratory docking</span></div>
  {error&&<div className="replay-error" role="alert">{error} <button onClick={()=>location.reload()}>Retry</button></div>}
  <main className="evidence-stage">
   <div className="scene-surface">{evidence&&<MolecularScene evidence={evidence} candidateSdf={dockPose?.sdf} view={view} contact={contact} onResidue={sequence=>{const c=evidence.contacts.find(c=>c.sequence===sequence);if(c)chooseContact(c);else setPickNote(`Residue A:${sequence} is not in the ≤4 Å contact list.`);}}/>}</div>
   <div className="scene-top"><div><span className="scene-kicker">EXPERIMENTAL REFERENCE · 8Y2G</span><h2>Dopamine transporter</h2><p>Bound ligand: dexmethylphenidate · cryo-EM, 2.83 Å</p></div><div className="camera-controls">{(['protein','pocket','ligand'] as const).map(v=><button key={v} className={view===v&&!contact?'active':''} onClick={()=>camera(v)}>{v[0].toUpperCase()+v.slice(1)}</button>)}<button onClick={()=>{setTour(!tour);setTourStep(0);setContact(null);setView('protein');}}>{tour?'Stop tour':'▶ Guided tour'}</button></div></div>
   <aside className="evidence-left">
    <details className="floating-panel" open><summary>Structural evidence <span>01</span></summary><div className="panel-content"><div className="evidence-pill">Reference complex · not a candidate pose</div><p>The reference ligand is <strong>dexmethylphenidate</strong>. None of the 160 demo compounds is an exact stereochemical match.</p><dl><div><dt>Target</dt><dd>Human DAT · Q01959</dd></div><div><dt>Protein / ligand chains</dt><dd>A / B (label IDs)</dd></div><div><dt>Structure</dt><dd><a href="https://www.rcsb.org/structure/8Y2G" target="_blank" rel="noreferrer">RCSB 8Y2G ↗</a></dd></div></dl><p className="quiet">Coordinates provide structural context; they do not enter the current ranking model.</p><details><summary>Provenance & construct</summary><p>{evidence?.construct_note}</p><a href="/structures/8y2g/manifest.json" target="_blank">Download source manifest ↗</a></details></div></details>
    <details className="floating-panel" open><summary>Nearby residues <span>≤ 4 Å</span></summary><div className="panel-content contact-list"><p className="quiet">Select a residue to highlight it in 3D. Distances are geometric proximity, not assigned hydrogen bonds.</p>{evidence?.contacts.map(c=><button key={c.sequence} className={contact?.sequence===c.sequence?'selected':''} onClick={()=>chooseContact(c)}><span>{c.residue} <b>{c.chain}:{c.sequence}</b></span><span>{c.distance.toFixed(2)} Å</span></button>)}{contact&&<p className="contact-detail">{contact.protein_atom} ↔ ligand {contact.ligand_atom}<br/>Minimum heavy-atom distance: {contact.distance.toFixed(2)} Å</p>}{pickNote&&<p role="status">{pickNote}</p>}</div></details>
   </aside>
   <aside className="evidence-right">
    <details className="floating-panel" open><summary>Recorded campaign <span>{round?`R${round.round}`:'—'}</span></summary><div className="panel-content"><label className="field-label" htmlFor="replay-campaign">Campaign</label><select id="replay-campaign" value={campaignId} onChange={e=>setCampaignId(e.target.value)} disabled={loading}>{campaigns.map(c=><option value={c.id} key={c.id}>{c.name} · {c.rounds.length} rounds</option>)}</select>{loading?<p role="status">Loading recorded decisions…</p>:round?<><div className="replay-stats"><div><strong>{round.training.length}</strong><span>measured at fit</span></div><div><strong>{round.eligible_count}</strong><span>eligible</span></div></div><p className="model-label">{round.recipe.model} <span>· {round.recipe.policy}</span></p><p className="quiet">{replay?.assay}</p>{!replay?.demo&&<p className="evidence-pill">The reference DAT structure is not verified against this imported campaign.</p>}<details><summary>Exact training snapshot</summary><code>{round.training_sha256}</code><div className="measurement-list">{round.training.map(r=><div key={r.compound_id}><span>{r.compound_id}</span><b>{fmt(r.value)}</b></div>)}</div></details></>:<p>No committed rounds yet. <Link href="/dashboard">Commit a batch in the dashboard</Link> to record a replay.</p>}</div></details>
    <details className="floating-panel" open><summary>{stage>=3?'Committed batch':'Prediction evidence'} <span>{stage>=2?replay?.endpoint:'waiting'}</span></summary><div className="panel-content">{directCompound?<><h3>{directCompound}</h3><p>Opened from the dashboard. This compound has no score in the saved rounds shown here; docking is separate from recorded decisions.</p><button onClick={()=>setDirectCompound(null)}>Return to recorded predictions</button></>:round&&stage>=2?<><div className="replay-ranking">{(stage>=3?round.recommendations:[...round.scored].sort((a,b)=>b.prediction-a.prediction).slice(0,8)).map((r,i)=><button key={r.compound_id} className={pick?.compound_id===r.compound_id?'selected':''} onClick={()=>setSelected(r.compound_id)}><span>{String(i+1).padStart(2,'0')}</span><span>{r.compound_id}</span><b>{fmt(r.prediction)}{priorScores.has(r.compound_id)&&<small className="prediction-change">Δ {fmt(r.prediction-priorScores.get(r.compound_id)!)}</small>}</b></button>)}</div>{roundIndex>0&&<p className="quiet">Δ compares the same compound with the previous recorded fit. No prior score means no displayed change.</p>}{pick&&<div className="chosen-evidence"><h3>{pick.compound_id}</h3><p>{stage<3?'Saved activity prediction. Advance to Select batch to inspect the recorded decision.':selectedRecommendation?.selection_reason==='user_locked'?'Locked into the batch by the researcher.':selectedRecommendation?'Selected for high predicted activity among eligible candidates.':'Scored candidate; not selected in this batch.'}</p><dl><div><dt>Nearest measured</dt><dd>{pick.nearest_measured_id}</dd></div><div><dt>Analog {replay?.endpoint} / similarity</dt><dd>{fmt(pick.nearest_measured_value)} / {fmt(pick.similarity)}</dd></div><div><dt>Recorded outcome</dt><dd>{stage>=4?result?.value!=null?fmt(result.value):result?.status||'Not recorded':'Not revealed at this step'}</dd></div></dl><p className="quiet">The reference is experimental. Use docking below to explore a hypothetical candidate pose.</p><button className="dock-shortcut" onClick={()=>document.querySelector(".docking-panel")?.scrollIntoView({block:"nearest",behavior:"smooth"})}>Dock / compare in 3D ↓</button></div>}</>:<p className="quiet">Advance to Score candidates to reveal saved predictions. No outcomes are shown before the results step.</p>}</div></details>
    {(directCompound||pick)&&stage>=2&&replay&&<DockingPanel key={`${campaignId}:${directCompound||pick!.compound_id}`} campaignId={campaignId} compoundId={directCompound||pick!.compound_id} demo={replay.demo} contacts={evidence?.contacts||[]} onPose={setDockPose}/>}
   </aside>
   <div className="scene-caption"><span className="reference-dot"/>Reference ligand {dockPose&&<><span className="candidate-dot"/>Predicted candidate</>} <span className="protein-dot"/>Protein & pocket <span>Drag to orbit · scroll to zoom</span><p>Camera tour of a static structure · not a binding trajectory</p></div>
  </main>
  <section className="replay-bottom"><div className="timeline-panel"><div className="timeline-title"><h2>Decision timeline</h2><span>{round?`Round ${round.round} / ${replay?.rounds.length}`:'No recorded round'}</span></div><div className="replay-steps">{stages.map((name,i)=><button key={name} aria-current={stage===i?'step':undefined} className={stage===i?'active':''} disabled={!round} onClick={()=>{setPlaying(false);setStage(i);}}><small>0{i+1}</small>{name}</button>)}</div><p className="stage-explanation" aria-live="polite">{stageText||'Your saved campaign decisions will appear here.'}</p><div className="playback-controls"><button className="play-button" disabled={!steps} onClick={()=>{if(position===steps-1)seek(0);setPlaying(!playing);}}>{playing?'Pause':'▶ Play'}</button><button disabled={!steps||position>=steps-1} onClick={()=>{setPlaying(false);seek(position+1);}}>Step →</button><button disabled={!steps} onClick={()=>{setPlaying(false);seek(0);}}>Restart</button><label>Speed <select value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={0.5}>½×</option><option value={1}>1×</option><option value={2}>2×</option></select></label><label>Round <select value={roundIndex} disabled={!steps} onChange={e=>{setPlaying(false);setRoundIndex(Number(e.target.value));setStage(0);setSelected('');}}>{replay?.rounds.map((r,i)=><option value={i} key={r.round}>{r.round}</option>)}</select></label></div><input className="timeline-scrubber" type="range" min={0} max={Math.max(steps-1,1)} value={position} disabled={!steps} aria-label="Recorded decision step" onChange={e=>{setPlaying(false);seek(Number(e.target.value));}}/><p className="quiet">Replays saved artifacts. Playback does not run experiments, retrain, or change the campaign.</p></div>
   <div className="outcome-panel"><div className="timeline-title"><h2>Prediction → observation</h2><span>{stage>=4&&values.length?`Batch MAE ${fmt(mae)}`:'Outcomes hidden'}</span></div>{stage>=4&&values.length?<><div className="outcome-table"><div className="outcome-row heading"><span>Compound</span><span>Predicted</span><span>Observed</span><span>Error</span></div>{values.map(r=><div className="outcome-row" key={r.compound_id}><span>{r.compound_id}</span><span>{fmt(r.prediction)}</span><span>{fmt(r.observed)}</span><span className={Math.abs(r.prediction-r.observed)>1?'large-error':''}>{fmt(r.prediction-r.observed)}</span></div>)}</div><p className="quiet">{replay?.demo?'Existing public measurements, revealed retrospectively.':'Recorded imported outcomes.'} This selected-batch error is not an independent test-set metric.</p></>:<div className="outcome-empty"><span>Measure, then compare.</span><p>Recorded outcomes become visible at Reveal results. Missing measurements remain unavailable.</p></div>}</div>
  </section>
  <footer className="replay-footer">Mol* molecular rendering · RCSB experimental coordinates · Aster recorded campaign evidence <a href="/structures/8y2g/manifest.json">Provenance manifest ↗</a></footer>
 </div>;
}
