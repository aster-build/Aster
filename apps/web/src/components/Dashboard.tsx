'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { LogoMark, Wordmark } from '@/components/Logo';
import { api, base, type Campaign, type CampaignSummary, type Compound, type Job, type Preview, type Score } from '@/lib/campaign-api';
import { ResizableWorkspace } from '@/components/ResizableWorkspace';
import { WorkflowSteps } from '@/components/WorkflowSteps';
import { KeyHint } from '@/components/ui';
import './dashboard.css';

function message(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong. Please try again.'; }
const number = (value?: number | null) => value == null ? '—' : value.toFixed(2);

export default function Dashboard() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState('');
  const [viewRound, setViewRound] = useState<number | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showImport, setShowImport] = useState(false);
  const [batchSize, setBatchSize] = useState(8);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(0);
  const shortlistRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const resultFile = useRef<HTMLInputElement>(null);
  const activeId = useRef('');

  const loadCampaign = useCallback(async (id: string, preserve = false) => {
    activeId.current = id;
    const result = await api<Campaign>(`/campaigns/${id}`);
    if (activeId.current !== id) return;
    setCampaign(result); localStorage.setItem('aster-campaign', id);
    if (!preserve) {
      setPreview(null); setViewRound(result.rounds.length ? result.rounds.length : null); setSelected(''); setJob(null);
      const pendingJob = localStorage.getItem(`aster-job-${id}`);
      if (pendingJob) {
        try { const saved = await api<Job>(`/jobs/${pendingJob}`); if (activeId.current === id) setJob(saved); }
        catch { localStorage.removeItem(`aster-job-${id}`); }
      }
    }
  }, []);
  const refreshList = useCallback(async () => { const rows = await api<CampaignSummary[]>('/campaigns'); setCampaigns(rows); return rows; }, []);

  useEffect(() => { let live = true;
    refreshList().then(rows => { if (!live || !rows.length) return; const last = localStorage.getItem('aster-campaign'); return loadCampaign(rows.find(r => r.id === last)?.id || rows[0].id); }).catch(e => { if (live) setError(message(e)); });
    return () => { live = false; };
  }, [refreshList, loadCampaign]);

  useEffect(() => {
    if (!job || !campaign) return;
    let live = true; const id = campaign.id; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const status = await api<Job>(`/jobs/${job!.id}`);
        if (!live || activeId.current !== id) return;
        if (status.status === 'complete' && status.preview_id) {
          const result = await api<Preview>(`/campaigns/${id}/previews/${status.preview_id}`);
          if (!live || activeId.current !== id) return;
          setPreview(result); setViewRound(null); setSelected(result.recommendations[0]?.compound_id || ''); setJob(null);
          localStorage.removeItem(`aster-job-${id}`); setNotice('Preview ready. Review the batch before committing.');
        } else if (status.status === 'failed') { setError(status.error || 'Preview failed. Try again.'); setJob(null); localStorage.removeItem(`aster-job-${id}`); }
        else { timer = setTimeout(poll, 700); }
      } catch (e) { if (live) { setError(message(e)); setJob(null); } }
    }
    poll(); return () => { live = false; clearTimeout(timer); };
  }, [job, campaign]);

  async function action(label: string, operation: () => Promise<void>) {
    setBusy(label); setError(''); setNotice('');
    try { await operation(); } catch (e) { setError(message(e)); } finally { setBusy(''); }
  }
  async function createDemo() { await action('Loading public data', async () => {
    const result = await api<{id: string}>('/demo', {}); await refreshList(); await loadCampaign(result.id); setNotice('Public campaign created: 32 measurements and 128 candidates. Preview your first batch.');
  }); }
  async function startPreview() { if (!campaign) return; await action('Starting model', async () => {
    const result = await api<{job_id: string}>(`/campaigns/${campaign.id}/previews`, {batch_size: batchSize});
    localStorage.setItem(`aster-job-${campaign.id}`, result.job_id); setJob({id: result.job_id, status: 'queued'});
  }); }
  async function commit() { if (!campaign || !preview) return; await action('Committing batch', async () => {
    const result = await api<{round: number}>(`/campaigns/${campaign.id}/commit`, {preview_id: preview.id});
    await loadCampaign(campaign.id, true); await refreshList(); setViewRound(result.round); setNotice(`Round ${result.round} committed. Export the batch or import its results.`);
  }); }
  async function constraint(compound: Compound, mode: string) { if (!campaign) return; await action('Saving constraint', async () => {
    await api(`/campaigns/${campaign.id}/constraints`, {ids: [compound.compound_id], mode, revision: campaign.revision});
    await loadCampaign(campaign.id, true); setPreview(null); setViewRound(null); setNotice('Constraint saved. Generate a fresh preview to apply it.');
  }); }

  const latest = campaign?.rounds.at(-1);
  const pending = campaign?.rounds.find(r => r.status === 'pending');
  const round = viewRound ? campaign?.rounds.find(r => r.round === viewRound) : undefined;
  const recommendations = round?.recommendations || preview?.recommendations || [];
  const stale = !!preview && !round && preview.revision !== campaign?.revision;
  const proposalIds = new Set(recommendations.map(r => r.compound_id));
  const scoreRows: Score[] = round ? (preview && preview.id === round.preview_id ? preview.scored : round.recommendations) : preview?.scored || [];
  const scores = new Map(scoreRows.map(s => [s.compound_id, s]));
  const inspected = campaign?.compounds.find(c => c.compound_id === selected) || campaign?.compounds.find(c => c.compound_id === recommendations[0]?.compound_id);
  const inspectedScore = inspected ? scores.get(inspected.compound_id) : undefined;
  const inspectedPick = recommendations.find(c => c.compound_id === inspected?.compound_id);
  const rows = (campaign?.compounds || []).filter(c => (filter === 'all' || (filter === 'proposed' ? proposalIds.has(c.compound_id) : c.status === filter)) && c.compound_id.toLowerCase().includes(search.toLowerCase()));
  const counts = { measured: campaign?.compounds.filter(c => c.status === 'measured').length || 0, available: campaign?.compounds.filter(c => c.status === 'available').length || 0 };
  const waiting = !!busy || !!job;

  async function importResults(file: File) { if (!campaign || !pending) return; await action('Importing results', async () => {
    const result = await api<{added: number; round_status: string}>(`/campaigns/${campaign.id}/rounds/${pending.round}/results`, {csv: await file.text()});
    await loadCampaign(campaign.id, true); await refreshList(); setNotice(`${result.added} results added. Round ${pending.round} is ${result.round_status}.`);
  }); }

  return <div className="workspace">
    <header className="workspace-nav"><Link href="/" className="workspace-brand"><Wordmark /><span className="nav-divider">/</span><span className="nav-context">Workspace</span></Link><div className="nav-right"><Link href="/replay">3D evidence ↗</Link><span className="local-badge"><i />Local research prototype</span></div></header>
    <main className="workspace-main">
      <div className="workspace-heading"><div><div className="eyebrow">CAMPAIGN WORKSPACE</div><h1>Your next experiment.</h1><p>A clear path from measured compounds to a considered next batch.</p></div><button className="button" onClick={() => setShowImport(true)} disabled={waiting}>＋ Import campaign</button></div>
      {error && <div role="alert" className="banner error"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
      {notice && <div role="status" className="banner success">{notice}</div>}
      {!campaign ? <section className="empty-workspace"><div className="empty-orbit"><LogoMark className="size-12" /></div><div className="eyebrow">YOUR FIRST CAMPAIGN</div><h2>Start with what you know.</h2><p>Bring measured compounds and an untested candidate library.<br />Aster turns those observations into a reviewable next batch.</p><div className="empty-actions"><button className="button primary" onClick={() => setShowImport(true)}>Import your CSVs</button><button className="button" onClick={createDemo} disabled={waiting}>{busy || 'Try a public-data campaign →'}</button></div><div className="empty-note">The public replay uses real, previously measured data.<br />It demonstrates the workflow—not a new discovery claim.</div></section> : <>
        <section className="campaign-strip"><div className="campaign-picker"><label htmlFor="campaign-select">CAMPAIGN</label><select id="campaign-select" value={campaign.id} disabled={waiting} onChange={e => action('Loading campaign', () => loadCampaign(e.target.value))}>{campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select><span>{campaign.assay}</span></div><div className="campaign-stat"><strong>{counts.measured}</strong><span>measured</span></div><div className="campaign-stat"><strong>{counts.available}</strong><span>untested</span></div><div className="campaign-stat"><strong>{campaign.rounds.filter(r => r.status === 'complete').length}</strong><span>completed rounds</span></div><div className="model-badge"><span>REFERENCE MODEL</span><strong>Morgan + ridge</strong><small>Greedy selection · {campaign.endpoint}</small></div></section>
        {campaign.demo && <div className="demo-note"><span>PUBLIC-DATA REPLAY</span> Existing measurements are revealed only after you commit a batch. No new laboratory experiments are being run.<button onClick={createDemo} disabled={waiting}>Start fresh ↗</button></div>}
        <section className="campaign-window">
          <div className="window-top"><LogoMark className="size-[18px] shrink-0" /><strong className="window-campaign">{campaign.name}</strong><span aria-hidden="true">/</span><span>{round ? `Round ${round.round} · ${round.status}` : preview ? `Round ${preview.round} · review preview` : `Round ${(latest?.round || 0)+1} · ready to predict`}</span><span className="real-badge">Saved campaign data</span></div>
          <div className="workflow-bar"><WorkflowSteps current={pending ? 2 : preview && !round ? 1 : latest?.status === "complete" && round ? 3 : 0} /><div className="workflow-detail">Morgan + ridge · reference model</div></div>
          <div className="dashboard-toolbar"><div><h2>{pending ? 'Ready to test' : 'Prioritize the next batch'}</h2><p>{pending ? 'Export the committed batch, then import exact measurements or failed assay statuses.' : 'Activity predictions, observed analogs, and the constraints you choose.'}</p></div><div className="toolbar-actions"><label>Batch size<input aria-label="Batch size" type="number" min="1" max="64" value={batchSize} disabled={!!pending || waiting} onChange={e => setBatchSize(Number(e.target.value))} /></label><button className="button primary" onClick={startPreview} disabled={!!pending || waiting || !Number.isInteger(batchSize) || batchSize < 1 || batchSize > 64}>{job ? 'Fitting model…' : busy || (preview ? 'Refresh preview' : 'Preview next batch')}<span>↗</span></button></div></div>
          <ResizableWorkspace><section className="map-panel"><div className="panel-heading"><h3>Candidate landscape</h3><span>{scoreRows.length ? `${scoreRows.length} scored` : 'Awaiting model preview'}</span></div>
            <CandidatePlot scores={scoreRows} selected={inspected?.compound_id} proposed={proposalIds} onSelect={setSelected} endpoint={campaign.endpoint} />
            <div className="map-legend"><span><i className="dot faint" />Candidate</span><span><i className="dot violet" />In batch</span><span><i className="dot ring" />Selected</span></div><p className="map-caption">Similarity is proximity to a measured compound—not confidence. {round && scoreRows.length === recommendations.length ? 'This saved view shows the committed batch.' : 'Higher predictions rank first, after your locks and exclusions.'}</p>
          </section><section className="inspector"><div className="inspector-structure"><div className="inspector-label">Selected compound{inspectedPick ? ` · pick ${inspectedPick.rank} of ${recommendations.length}` : ""}</div><div className="inspector-title"><h3>{inspected?.compound_id || 'The evidence behind the choice'}</h3>{inspected && <span className="status-pill">{inspected.status}</span>}</div>{inspected ? <img width="360" height="200" src={`${base}/campaigns/${campaign.id}/molecule?compound_id=${encodeURIComponent(inspected.compound_id)}`} alt={`Molecular structure of ${inspected.compound_id}`} /> : <div className="structure-placeholder">Select a compound to inspect its structure.</div>}</div><div className="inspector-evidence">{inspected&&<Link className="button small" href={`/replay?campaign=${campaign.id}&compound=${encodeURIComponent(inspected.compound_id)}`}>Explore 3D docking ↗</Link>}<div className="evidence-heading">{round ? "Why it was selected" : "Why test it next"}</div><p>{inspectedPick ? inspectedPick.selection_reason === 'user_locked' ? 'Included because you locked this compound into the batch.' : 'Selected by predicted activity among eligible candidates, after applying your constraints.' : inspected?.status === 'measured' ? 'An observed measurement available to future model fits.' : 'Inspect the structure, score, and nearest observed analog before choosing what to measure.'}</p><dl className="evidence-grid"><div><dt>Predicted {campaign.endpoint}</dt><dd>{number(inspectedScore?.prediction)}</dd></div><div><dt>Nearest assayed</dt><dd className="analog-id">{inspectedScore?.nearest_measured_id || '—'} <span>· sim {number(inspectedScore?.similarity)} · measured {number(inspectedScore?.nearest_measured_value)}</span></dd></div>{inspected?.value != null && <div><dt>Observed {campaign.endpoint}</dt><dd>{number(inspected.value)}</dd></div>}</dl>{inspectedPick?.outside_diagnostic_range && <p className="stale-warning">Prediction outside the diagnostic range [0,14]. Review before use; no clipping was applied.</p>}{inspected?.status === 'available' && <div className="constraint-actions"><button className="button small" disabled={waiting || !!pending} onClick={() => constraint(inspected, inspected.constraint === 'locked' ? 'available' : 'locked')}>{inspected.constraint === 'locked' ? 'Unlock compound' : 'Lock into next batch'}</button><button className="button small" disabled={waiting || !!pending} onClick={() => constraint(inspected, inspected.constraint === 'excluded' ? 'available' : 'excluded')}>{inspected.constraint === 'excluded' ? 'Restore eligibility' : 'Exclude compound'}</button><span>Constraint: {inspected.constraint}</span></div>}</div></section>
          <section className="shortlist-panel"><div className="panel-heading"><h3>{round ? 'Committed batch' : 'Proposed batch'}</h3><span>{recommendations.length ? `${recommendations.length} compounds` : 'Not generated'}</span></div>{!recommendations.length ? <div className="panel-empty"><span>01</span><h3>Let the measurements lead.</h3><p>Preview a batch to train on your observed data and rank eligible candidates.</p></div> : <><div className="shortlist-columns" aria-hidden="true"><span>#</span><span>Compound</span><span>Predicted {campaign.endpoint}</span><span>Similarity</span><span>Selection reason</span></div><div className="shortlist" onKeyDown={e => {
              if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
              e.preventDefault();
              const current = recommendations.findIndex(r => r.compound_id === inspected?.compound_id);
              const next = Math.max(0, Math.min(recommendations.length - 1, current + (e.key === 'ArrowDown' ? 1 : -1)));
              setSelected(recommendations[next].compound_id); shortlistRefs.current[next]?.focus();
            }}>{recommendations.map((r, index) => <button ref={el => {shortlistRefs.current[index] = el;}} aria-pressed={inspected?.compound_id === r.compound_id} key={r.compound_id} className={`shortlist-row ${inspected?.compound_id === r.compound_id ? 'selected' : ''}`} onClick={() => setSelected(r.compound_id)}><span className="rank">{String(r.rank).padStart(2,'0')}</span><span className="shortlist-id">{r.compound_id}</span><strong>{number(r.prediction)}<small>{campaign.endpoint}</small></strong><span className="shortlist-similarity">{number(r.similarity)}</span><span className="shortlist-reason">{r.selection_reason === "user_locked" ? "Locked by you" : "Highest predicted activity"}</span></button>)}</div></>}{stale && <p className="stale-warning">This preview is stale. Refresh it before committing.</p>}<div className="shortlist-footer">{round ? <a className="button full" href={`${base}/campaigns/${campaign.id}/rounds/${round.round}/export`}>↓ Export committed batch</a> : <button className="button primary full" disabled={!preview || stale || waiting || !!pending} onClick={commit}>Commit this batch →</button>}<small><KeyHint dir="up" /> <KeyHint dir="down" /> to inspect · {round ? "Predictions saved at decision time." : "Review before committing."}</small></div></section></ResizableWorkspace>
        </section>
        {pending && <section className="results-panel"><div><div className="eyebrow">CLOSE THE LOOP</div><h2>Bring round {pending.round} back to the model.</h2><p>{Object.keys(pending.results).length} of {pending.recommendations.length} outcomes recorded. Partial imports and failed assays are supported.</p></div><div className="results-actions"><a className="button" href={`${base}/campaigns/${campaign.id}/rounds/${pending.round}/export?template=true`}>↓ Results template</a><button className="button primary" onClick={() => resultFile.current?.click()} disabled={waiting}>Import results CSV</button><input ref={resultFile} type="file" accept=".csv,text/csv" className="sr-only" aria-label="Results CSV" onChange={e => { const f=e.target.files?.[0]; if(f) importResults(f); e.target.value=''; }} />{campaign.demo && <button className="text-button" disabled={waiting} onClick={() => action('Replaying public outcomes', async () => { await api(`/campaigns/${campaign.id}/rounds/${pending.round}/demo-results`, {}); await loadCampaign(campaign.id, true); await refreshList(); setNotice('Existing public outcomes imported. Preview the next batch to refit on the new observations.'); })}>Replay public outcomes →</button>}</div></section>}
        <div className="lower-grid"><section className="library-panel"><div className="panel-heading"><h3>Compound library <span>{campaign.compounds.length}</span></h3><input aria-label="Search compounds" placeholder="Find a compound…" value={search} onChange={e => {setSearch(e.target.value);setPage(0);}} /></div><div className="filter-tabs">{['all','available','measured','proposed','pending','failed'].map(f => <button key={f} className={filter === f ? 'active' : ''} onClick={() => {setFilter(f);setPage(0);}}>{f === 'available' ? 'Untested' : f[0].toUpperCase()+f.slice(1)}</button>)}</div><div className="table-scroll"><table><thead><tr><th>Compound</th><th>Status</th><th>Prediction</th><th>Measured</th><th>Constraint</th></tr></thead><tbody>{rows.slice(page*12,page*12+12).map(c => <tr key={c.compound_id} className={inspected?.compound_id === c.compound_id ? 'table-selected' : ''}><td><button onClick={() => setSelected(c.compound_id)}>{c.compound_id}</button></td><td>{c.status}</td><td>{number(scores.get(c.compound_id)?.prediction)}</td><td>{number(c.value)}</td><td>{c.constraint === 'available' ? '—' : c.constraint}</td></tr>)}</tbody></table>{!rows.length && <p className="no-rows">No matching compounds.</p>}</div><div className="pagination"><span>{rows.length} matching compounds</span><button disabled={page===0} onClick={() => setPage(page-1)}>← Previous</button><button disabled={(page+1)*12>=rows.length} onClick={() => setPage(page+1)}>Next →</button></div></section><aside className="history-panel"><div className="panel-heading"><h3>Decision history</h3><span>{campaign.rounds.length} rounds</span></div>{!campaign.rounds.length ? <p className="history-empty">Your first committed batch will appear here, with its original predictions and results.</p> : campaign.rounds.map(r => <button key={r.round} className={`history-row ${viewRound === r.round ? 'active' : ''}`} onClick={() => {setViewRound(r.round);setSelected(r.recommendations[0].compound_id);}}><span className="history-index">{r.round}</span><span><strong>Round {r.round}</strong><small>Trained on {r.training_count} measurements</small><small>{Object.keys(r.results).length}/{r.recommendations.length} results · {r.status}</small></span><span>↗</span></button>)}<div className="history-note"><strong>Decisions you can trace.</strong><p>Each round preserves its training snapshot, model, original predictions, and selection reasons.</p><span>{campaign.events.length} recorded events</span></div></aside></div>
      </>}
      <footer className="workspace-footer"><span>Aster · A research workspace for better experimental decisions.</span><span>Predictions are hypotheses. Measurements are evidence.</span></footer>
    </main>
    {showImport && <ImportDialog error={error} busy={waiting} onClose={() => setShowImport(false)} onSubmit={body => action('Validating campaign', async () => { const result=await api<{id:string}>('/campaigns',body); await refreshList(); await loadCampaign(result.id); setShowImport(false); setNotice('Campaign validated and saved. Preview your first batch.'); })} />}
    {busy && <div className="busy-indicator" role="status"><span />{busy}…</div>}
  </div>;
}

function CandidatePlot({scores, proposed, selected, onSelect, endpoint}: { scores: Score[]; proposed: Set<string>; selected?: string; onSelect: (id: string) => void; endpoint: string }) {
  const values=scores.map(r=>r.prediction); const low=Math.floor(Math.min(...values,4))-0.25; const high=Math.ceil(Math.max(...values,9))+0.25;
  const x=(v:number)=>58+v*480; const y=(v:number)=>290-(v-low)/(high-low)*238;
  return <div className="plot-wrap"><svg viewBox="0 0 580 350" role="img" aria-label={`Candidate predictions in ${endpoint} versus similarity to nearest measured compound`}>
    {[0,0.25,0.5,0.75,1].map(v=><g key={v}><line x1={x(v)} y1="40" x2={x(v)} y2="290" stroke="#e7e6e2" strokeDasharray="3 5"/><text x={x(v)} y="312" textAnchor="middle">{v.toFixed(2)}</text></g>)}
    {[0,0.25,0.5,0.75,1].map(v=>{const val=low+(high-low)*v;return <g key={v}><line x1="58" y1={y(val)} x2="538" y2={y(val)} stroke="#e7e6e2"/><text x="46" y={y(val)+4} textAnchor="end">{val.toFixed(1)}</text></g>;})}
    <text x="295" y="341" textAnchor="middle">Similarity to nearest measured compound →</text><text transform="translate(17,168) rotate(-90)" textAnchor="middle">Predicted {endpoint} →</text>
    {scores.map(r=><g key={r.compound_id} onClick={()=>onSelect(r.compound_id)} className="plot-point"><title>{r.compound_id}: {number(r.prediction)} {endpoint}, similarity {number(r.similarity)}</title>{selected === r.compound_id && <circle cx={x(r.similarity)} cy={y(r.prediction)} r="12" fill="#eeeafb" stroke="#5236c9"/>}<circle cx={x(r.similarity)} cy={y(r.prediction)} r={proposed.has(r.compound_id)?5.5:3.5} stroke={proposed.has(r.compound_id)?"#5236c9":"none"} strokeWidth="1.7" fill={selected === r.compound_id ? "#5236c9" : proposed.has(r.compound_id)?"white":r.constraint==='excluded'?'#dddddf':'#9a9da3'} opacity={r.constraint==='excluded'?0.4:0.85}/></g>)}
    {!scores.length && <g><text x="300" y="150" textAnchor="middle" className="plot-placeholder">Your candidate landscape starts here</text><text x="300" y="172" textAnchor="middle">Preview a batch to see real model predictions.</text></g>}
  </svg></div>;
}

function ImportDialog({error,busy,onClose,onSubmit}:{error:string;busy:boolean;onClose:()=>void;onSubmit:(body:unknown)=>Promise<void>}) {
  const [name,setName]=useState('');const [assay,setAssay]=useState('');const [endpoint,setEndpoint]=useState('pKi');const [measured,setMeasured]=useState<File|null>(null);const [candidates,setCandidates]=useState<File|null>(null);
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{dialog.current?.showModal();},[]);
  return <dialog ref={dialog} className="import-dialog" onCancel={e=>{if(busy)e.preventDefault();else onClose();}}><form onSubmit={async e=>{e.preventDefault();if(measured&&candidates)await onSubmit({name,assay,endpoint,measured_csv:await measured.text(),candidates_csv:await candidates.text()});}}><div className="dialog-heading"><div><div className="eyebrow">A NEW STARTING POINT</div><h2>Import a campaign</h2></div><button type="button" aria-label="Close import" onClick={onClose} disabled={busy}>×</button></div>{error && <p role="alert" style={{color:"#a04432"}}>{error}</p>}<p>One target, one compatible assay. At least 32 measured compounds, with exact pKi or pIC50 values.</p><label>Campaign name<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Kinase series · first pass" /></label><div className="form-grid"><label>Assay identifier<input required maxLength={250} value={assay} onChange={e=>setAssay(e.target.value)} placeholder="Your single assay ID" /></label><label>Endpoint<select value={endpoint} onChange={e=>setEndpoint(e.target.value)}><option>pKi</option><option>pIC50</option></select></label></div><label className="file-field">Measured compounds<input type="file" accept=".csv,text/csv" required onChange={e=>setMeasured(e.target.files?.[0]||null)} /><small>Exact columns: compound_id, smiles, value</small></label><label className="file-field">Untested candidates<input type="file" accept=".csv,text/csv" required onChange={e=>setCandidates(e.target.files?.[0]||null)} /><small>Exact columns: compound_id, smiles. No outcome values.</small></label><p className="import-hint">Values must already be −log10 of molar concentrations. Duplicate structures, mixtures, censored values, and incompatible columns are rejected.</p><button className="button primary full" disabled={busy}>{busy?'Validating…':'Validate and create campaign →'}</button></form></dialog>;
}
