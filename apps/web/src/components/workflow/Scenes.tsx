'use client';
import { useEffect, useRef, useState } from 'react';
import { thinkingCanvas } from './canvas';
import { api } from '@/lib/campaign-api';
import type { DockPose } from '@/components/DockingPanel';

import dynamic from 'next/dynamic';
import type { StructureEvidence } from '@/lib/replay';
const MolecularScene = dynamic(() => import('@/components/MolecularScene'), { ssr: false, loading: () => <div className="structure-status">Preparing molecular viewer…</div> });
const ignoreResidue = () => {};

export function ProteinScene({ sdf, overview=false }: { sdf?: string; overview?: boolean }) {
  const [evidence,setEvidence]=useState<StructureEvidence|null>(null), [error,setError]=useState('');
  useEffect(()=>{const abort=new AbortController();fetch('/structures/8y2g/manifest.json',{signal:abort.signal}).then(r=>{if(!r.ok)throw Error('Structure unavailable');return r.json();}).then(setEvidence).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();},[]);
  return <div className={`detailed-structure ${overview?'protein-canvas':'docking-canvas'}`}>
    {error ? <p role="alert" className="structure-status">{error}</p> : evidence ? <MolecularScene evidence={evidence} view={overview?'protein':'pocket'} contact={null} onResidue={ignoreResidue} candidateSdf={sdf} /> : <p role="status" className="structure-status">Loading experimental structure…</p>}
  </div>;
}
export function ThinkingScene({stage}:{stage:number}){const canvas=useRef<HTMLCanvasElement>(null),current=useRef(stage);useEffect(()=>{current.current=stage;},[stage]);useEffect(()=>canvas.current?thinkingCanvas(canvas.current,()=>current.current):undefined,[]);return <canvas ref={canvas} aria-label="Animated chemistry encoding, fitting and prediction workflow"/>;}
type DockJob={id:string;compound_id:string;status:string;error?:string;result?:{poses:DockPose[]}};
export function DockingView({campaignId,compoundId,demo}:{campaignId:string;compoundId:string;demo:boolean}){
  const [job,setJob]=useState<DockJob|null>(null),[rank,setRank]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false),[valid,setValid]=useState(false);
  useEffect(()=>{let live=true;Promise.all([api<{passed:boolean}>('/docking/validation'),api<DockJob[]>(`/campaigns/${campaignId}/docking`)]).then(async([v,jobs])=>{if(!live)return;setValid(v.passed);const found=jobs.find(j=>j.compound_id===compoundId);if(found){const result=await api<DockJob>(`/campaigns/${campaignId}/docking/${found.id}`);if(live)setJob(result);}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[campaignId,compoundId]);
  useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;let live=true;const timer=setTimeout(()=>api<DockJob>(`/campaigns/${campaignId}/docking/${job.id}`).then(j=>{if(live)setJob(j);}).catch(e=>{if(live)setError(e.message);}),1200);return()=>{live=false;clearTimeout(timer);};},[job,campaignId]);
  async function dock(){setBusy(true);setError('');try{const j=await api<{id:string}>(`/campaigns/${campaignId}/docking`,{compound_id:compoundId});setJob(await api<DockJob>(`/campaigns/${campaignId}/docking/${j.id}`));}catch(e){setError(e instanceof Error?e.message:'Docking failed');}finally{setBusy(false);}}
  const pose=job?.result?.poses[rank],running=busy||!!job&&['queued','running'].includes(job.status);
  return <>{demo?<ProteinScene sdf={pose?.passed?pose.sdf:undefined}/>:<p className="no-pose">This target needs its own validated structure before docking.</p>}<div className="docking-legend">Blue: experimental reference · Gold: predicted pose</div><div className="pose-controls">{job?.result?.poses.length?<label>Saved pose <select aria-label={`Pose for ${compoundId}`} value={rank} onChange={e=>setRank(Number(e.target.value))}>{job.result.poses.map((p,i)=><option key={p.rank} value={i}>Pose {p.rank} · {p.score_kcal_mol.toFixed(2)} kcal/mol{p.passed?'':' · rejected'}</option>)}</select></label>:<button className="btn small" disabled={!demo||!valid||running} onClick={dock}>{running?'Docking…':'Dock this compound'}</button>}</div>{!pose&&<p className="no-pose">{running?'The saved job will continue if you leave this view.':'No candidate pose loaded. The reference alone is not evidence of this compound’s binding.'}</p>}{pose&&!pose.passed&&<p role="status" className="no-pose">Pose not rendered: {pose.failed_checks.join(', ')}</p>}{(error||job?.error)&&<p role="alert" className="no-pose">{error||job?.error}</p>}</>;
}
