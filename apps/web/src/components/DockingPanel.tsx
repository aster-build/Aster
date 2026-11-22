'use client';
import {useEffect,useState} from 'react';
import {api,base} from '@/lib/campaign-api';
import type {Contact} from '@/lib/replay';
export type PoseInteraction={interaction:string;residue?:string;sequence?:number;chain?:string;role?:string;subtype?:string;distance_angstrom?:number;donor_acceptor_angstrom?:number;angle_degrees?:number};
type Proximity={residue:string;sequence:number;distance:number};
// `interactions` comes from the PLIP audit. `proximity_contacts` is the old ≤4 Å list,
// kept for 3D highlighting; `contacts` is the same list under its old name, in results
// saved before the audit existed.
export type DockPose={rank:number;score_kcal_mol:number;passed:boolean;failed_checks:string[];sdf:string;interactions?:PoseInteraction[];interaction_status?:string;proximity_contacts?:Proximity[];contacts?:Proximity[]};
const INTERACTION_DISTANCE=(i:PoseInteraction)=>i.distance_angstrom??i.donor_acceptor_angstrom;
type Validation={status:string;passed:boolean;reason:string;successful_seeds?:number;runs?:{seed:number;top1_rmsd:number;best_top5_rmsd:number;gate_pass:boolean}[]};
type Job={id:string;compound_id:string;status:string;error?:string;result?:{poses:DockPose[]}};
export default function DockingPanel({campaignId,compoundId,demo,contacts,onPose}:{campaignId:string;compoundId:string;demo:boolean;contacts:Contact[];onPose:(pose:DockPose|null)=>void}){
 const [validation,setValidation]=useState<Validation|null>(null);const [job,setJob]=useState<Job|null>(null);
 const [error,setError]=useState('');const [submitting,setSubmitting]=useState(false);const [rank,setRank]=useState(0);const [overlay,setOverlay]=useState(true);
 useEffect(()=>{let live=true;api<Validation>('/docking/validation').then(v=>{if(live)setValidation(v);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
 useEffect(()=>{let live=true;api<Job[]>(`/campaigns/${campaignId}/docking`).then(rows=>{const saved=rows.find(j=>j.compound_id===compoundId);if(saved)return api<Job>(`/campaigns/${campaignId}/docking/${saved.id}`);return null;}).then(j=>{if(live)setJob(j);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[campaignId,compoundId]);
 useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;let live=true;const timer=setTimeout(()=>api<Job>(`/campaigns/${campaignId}/docking/${job.id}`).then(j=>{if(live)setJob(j);}).catch(e=>{if(live)setError(e.message);}),1500);return()=>{live=false;clearTimeout(timer);};},[job,campaignId]);
 const pose=job?.result?.poses[rank];
 useEffect(()=>{onPose(overlay&&pose?.passed?pose:null);return()=>onPose(null);},[overlay,pose,onPose]);
 async function dock(){setSubmitting(true);setError('');try{const j=await api<Job>(`/campaigns/${campaignId}/docking`,{compound_id:compoundId});setJob(await api<Job>(`/campaigns/${campaignId}/docking/${j.id}`));setRank(0);}catch(e){setError(e instanceof Error?e.message:'Docking failed');}finally{setSubmitting(false);}}
 const busy=submitting||job?.status==='queued'||job?.status==='running';
 const reference=new Set(contacts.map(c=>c.sequence));
 const named=pose?.interactions||[];const nearby=pose?.proximity_contacts||pose?.contacts||[];
 return <details className="floating-panel docking-panel" open><summary>Explore a docked pose <span>7B · exploratory</span></summary><div className="panel-content">
  <p className="quiet">{compoundId} → human DAT · 8Y2G</p>
  <p className="evidence-pill">{validation?.passed?'Redocking passed · cross-docking untested':validation?.status||'Checking validation…'}</p>
  <p className="quiet">Protein-only, rigid docking. Nearby ions are omitted from scoring. A pose is a hypothesis, not an observed interaction.</p>
  <button className="dock-action" disabled={!demo||!validation?.passed||busy} onClick={dock}>{busy?`${job?.status==='running'?'Docking':'Queued'}…`:job?.status==='complete'?'Load saved docking':'Dock selected compound'}</button>
  {!demo&&<p>Only the verified DAT demo is supported. Imported targets need their own receptor validation.</p>}
  {!validation?.passed&&validation&&<p>{validation.reason}</p>}
  {busy&&<p role="status">Saved job · at most two CPU threads. You can leave and return.</p>}
  {(error||job?.error)&&<p role="alert">{error||job?.error}</p>}
  {job?.status==='complete'&&job.result&&<><label className="field-label" htmlFor="dock-pose">Alternative poses (Vina order)</label><select id="dock-pose" value={rank} onChange={e=>setRank(Number(e.target.value))}>{job.result.poses.map((p,i)=><option key={p.rank} value={i}>Pose {p.rank} · {p.score_kcal_mol.toFixed(2)} kcal/mol · {p.passed?'checks pass':'rejected'}</option>)}</select>{pose&&<><p className="quiet">Score is not pKi or binding probability. Recommendations remain unchanged.</p>{pose.passed?<label className="dock-overlay"><input type="checkbox" checked={overlay} onChange={e=>setOverlay(e.target.checked)}/>Overlay candidate (lemon yellow) on reference (cornflower blue)</label>:<p role="status">Not rendered: {pose.failed_checks.join(', ')}.</p>}<div className="docked-contacts"><strong>Named interactions · PLIP</strong>{named.map((i,n)=><div key={`${i.interaction}:${i.chain}:${i.sequence}:${n}`}><span>{i.interaction.replace(/_/g,' ')}{i.subtype?` (${i.subtype})`:''}</span><span>{i.residue} {i.sequence}{INTERACTION_DISTANCE(i)!==undefined?` · ${INTERACTION_DISTANCE(i)!.toFixed(2)} Å`:''}{i.angle_degrees!==undefined?` · ${i.angle_degrees.toFixed(0)}°`:''}</span></div>)}{named.length===0&&<div><span className="quiet">{pose.interaction_status==='complete'?'No interaction met PLIP\u2019s geometric criteria for this pose.':'Interaction audit unavailable for this result; the nearby-residue list below is proximity only.'}</span></div>}</div><p className="quiet">Each interaction is named from pose geometry and assigned protonation, not measured. It is not a bond strength.</p><details className="docked-contacts"><summary>Nearby residues · ≤4 Å (proximity only)</summary>{nearby.map(c=><div key={c.sequence}><span>{c.residue} {c.sequence}</span><span>{c.distance.toFixed(2)} Å · {reference.has(c.sequence)?'shared':'new'}</span></div>)}</details></>}<a href={`${base}/campaigns/${campaignId}/docking/${job.id}`} target="_blank" rel="noreferrer">Saved poses, checks & provenance ↗</a></>}
  <details><summary>Validation results</summary><p>{validation?.reason}</p>{validation?.runs?.map(r=><p key={r.seed} className="quiet">Seed {r.seed}: top 1 {r.top1_rmsd.toFixed(2)} Å · best 5 {r.best_top5_rmsd.toFixed(2)} Å · {r.gate_pass?'pass':'fail'}</p>)}<a href={`${base}/docking/validation`} target="_blank" rel="noreferrer">Full validation report ↗</a></details>
 </div></details>;
}
