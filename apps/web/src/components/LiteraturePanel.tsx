'use client';

import { useEffect, useState } from 'react';
import { api, base, type Campaign, type Compound } from '@/lib/campaign-api';
import './literature.css';

type Claim = {
  id: string; title: string; authors: string; url: string; published: string; publication_precision: string;
  document_id: string; document_aliases: string[]; resolved_document_id: string; license: string;
  locator: string; passage: string; source_sha256: string; source_file: string | null;
  assay: string; assay_id: string | null; compound_id: string | null; compound_smiles: string | null;
  endpoint: string; value: number | null; unit: string | null; relation: string | null;
  evidence_type: string; source_kind: string; review_method: string; reviewer: string;
  match_type: string; similarity?: number; notices?: { kind: string; url: string; note: string }[];
};
type Result = { status: string; snapshot_sha256: string | null; claims: Claim[]; total_matches?: number;
  conflicts: { message: string; claim_ids: string[] }[]; scope: string; method: string };
type Query = { q: string; compound_id: string; scope: string; endpoint?: string; evidence_type?: string; cutoff?: string; method: string };
type Saved = { id: string; record: { query: Query; result: Result; timing: string } };

export default function LiteraturePanel({ campaign, compound, round }: { campaign: Campaign; compound: Compound; round: number | null }) {
  const [query, setQuery] = useState('dopamine binding');
  const [scope, setScope] = useState('exact');
  const [endpoint, setEndpoint] = useState('');
  const [kind, setKind] = useState('');
  const [cutoff, setCutoff] = useState('');
  const [method, setMethod] = useState('lexical');
  const [result, setResult] = useState<Result | null>(null);
  const [submitted, setSubmitted] = useState<Query | null>(null);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let active = true;
    if (round !== null) api<Saved[]>(`/campaigns/${campaign.id}/rounds/${round}/evidence`).then(rows => { if (active) setSaved(rows); }).catch(() => { if (active) setError('Saved evidence could not be loaded.'); });
    return () => { active = false; };
  }, [campaign.id, round]);
  const current: Query = { q: query, compound_id: compound.compound_id, scope, ...(endpoint && { endpoint }), ...(kind && { evidence_type: kind }), ...(cutoff && { cutoff }), method };
  const stale = !!submitted && JSON.stringify(current) !== JSON.stringify(submitted);
  async function search(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice(''); setResult(null);
    try {
      const response = await api<Result>(`/campaigns/${campaign.id}/evidence?${new URLSearchParams(current).toString()}`);
      setResult(response); setSubmitted(current);
    } catch (e) { setError(e instanceof Error ? e.message : 'Evidence search failed.'); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!submitted || !result?.snapshot_sha256 || round === null) return;
    setBusy(true); setError('');
    try {
      const record = await api<Saved>(`/campaigns/${campaign.id}/rounds/${round}/evidence`, { ...submitted, snapshot_sha256: result.snapshot_sha256 });
      setSaved(previous => [...previous.filter(item => item.id !== record.id), record]);
      setNotice(`Evidence saved to round ${round}. The original selection is unchanged.`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save evidence.'); }
    finally { setBusy(false); }
  }
  if (!campaign.demo) return <section className="literature-panel"><h3>Literature evidence</h3><p>Verify this campaign’s target before linking literature. The current corpus covers human dopamine transporter only.</p></section>;
  return <section className="literature-panel" aria-label="Literature evidence">
    <div className="literature-title"><div><span className="eyebrow">SOURCE-BACKED REVIEW</span><h3>Literature evidence</h3></div><span className="status-pill">Human DAT · Q01959</span></div>
    <p className="literature-intro">Review published findings for <strong>{compound.compound_id}</strong>. Literature does not change its prediction or batch ranking. This small corpus has machine-audited sources; independent scientific review is pending.</p>
    <form onSubmit={search} className="literature-form">
      <label className="literature-query">Search source passages<input required maxLength={500} value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. zinc, allosteric inhibition, binding" /></label>
      <label>Evidence relationship<select value={scope} onChange={e => setScope(e.target.value)}><option value="exact">Exact compound only</option><option value="analog">Related compounds · similarity ≥ 0.70</option><option value="target">Target context · not compound evidence</option></select></label>
      <label>Endpoint<select value={endpoint} onChange={e => setEndpoint(e.target.value)}><option value="">All endpoints</option><option value="Ki">Ki · reported affinity</option><option value="target_context">Target context</option></select></label>
      <label>Evidence type<select value={kind} onChange={e => setKind(e.target.value)}><option value="">All types</option><option value="experimental">Experimental</option><option value="computational">Computational</option><option value="context">Review / context</option></select></label>
      <label>Published on or before<input type="date" value={cutoff} onChange={e => setCutoff(e.target.value)} /></label>
      <label>Search method<select value={method} onChange={e => setMethod(e.target.value)}><option value="lexical">Keyword search</option><option value="hybrid">Keyword + text similarity · experimental</option></select></label>
      <button className="button primary" disabled={busy}>{busy ? 'Working…' : 'Search evidence'}</button>
    </form>
    {error && <p role="alert" className="banner error">{error}</p>}{notice && <p role="status" className="banner success">{notice}</p>}
    {stale && <p className="stale-warning">Filters changed. Search again to update these results.</p>}
    {result && <div className="literature-results" aria-live="polite">
      {result.status === 'corpus_unavailable' ? <p className="literature-empty">The literature corpus is not installed. Build the DAT corpus locally to enable search.</p> : result.claims.length === 0 ? <p className="literature-empty"><strong>No supporting records in this corpus.</strong> This does not mean the compound is inactive. Try target context to explore general findings, or broaden the query.</p> : <>
        <div className="literature-result-heading"><strong>{result.claims.length} of {result.total_matches} matching records</strong><span>Source excerpts · no generated potency claims</span></div>
        {result.conflicts.map((conflict, index) => <div key={index} className="literature-conflict"><strong>Measurement disagreement</strong><p>{conflict.message}</p><small>{conflict.claim_ids.join(' · ')}</small></div>)}
        {result.claims.map(c => <article key={c.id} className="literature-card">
          <div className="literature-tags"><span>{c.match_type === 'exact_compound' ? 'Exact compound' : c.match_type === 'analog' ? `Related compound · similarity ${c.similarity?.toFixed(2)}` : 'Target context'}</span><span>{c.evidence_type}</span><span>{c.review_method === 'human' ? 'Human reviewed' : c.review_method === 'machine' ? 'Machine audit · independent review pending' : 'Review method unspecified'}</span></div>
          <h4><a href={c.url} target="_blank" rel="noreferrer">{c.title} ↗</a></h4><p className="literature-authors">{c.authors} · {c.publication_precision === 'year' ? c.published.slice(0, 4) : c.published}</p>
          {c.value !== null && <p className="literature-measurement">{c.compound_id} · {c.endpoint} {c.relation} {c.value} {c.unit}<small>Reported assay measurement; not a prediction for the selected candidate.</small></p>}
          <blockquote>{c.passage}</blockquote>
          {c.notices?.map(notice => <p key={notice.url} className="literature-conflict"><a href={notice.url} target="_blank" rel="noreferrer">{notice.kind} ↗</a> · {notice.note}</p>)}
          <details><summary>Inspect citation, assay and provenance</summary><dl><dt>Source locator</dt><dd>{c.locator}</dd><dt>Assay / scope</dt><dd>{c.assay}</dd><dt>Document identifiers</dt><dd>{[c.document_id, ...c.document_aliases].join(' · ')}</dd><dt>Reuse terms</dt><dd>{c.license}</dd><dt>Review</dt><dd>{c.reviewer}</dd><dt>Source checksum</dt><dd>{c.source_sha256}</dd>{c.compound_smiles && <><dt>Source compound</dt><dd>{c.compound_smiles}</dd></>}</dl>{c.source_file && <a className="button small" href={`${base}/evidence/sources/${encodeURIComponent(c.source_file)}`}>Download pinned source</a>}</details>
        </article>)}
      </>}
      {result.snapshot_sha256 && <div className="literature-save"><small>Corpus snapshot {result.snapshot_sha256.slice(0, 12)} · Publication filters alone do not make this a blind evaluation.</small><button className="button" disabled={busy || stale || round === null} onClick={save}>Save evidence to {round === null ? 'a committed round' : `round ${round}`}</button>{round === null && <small>Commit a batch first to attach an evidence record.</small>}</div>}
    </div>}
    {saved.length > 0 && <details className="literature-saved"><summary>{saved.length} saved evidence {saved.length === 1 ? 'record' : 'records'} for round {round}</summary>{saved.map(item => <div key={item.id}><strong>{item.record.query.q}</strong><p>{item.record.timing}</p><small>{item.record.result.claims.length} records · snapshot {item.record.result.snapshot_sha256?.slice(0, 12)}</small><button className="button small" onClick={() => { const file = new Blob([JSON.stringify(item.record, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(file); const link = document.createElement('a'); link.href = url; link.download = `evidence-${item.id.slice(0, 12)}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}>Download saved evidence</button></div>)}</details>}
  </section>;
}
