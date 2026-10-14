export type Compound = { compound_id: string; smiles: string; status: 'available' | 'measured' | 'pending' | 'failed'; value: number | null; constraint: string };
export type Score = { compound_id: string; prediction: number; similarity: number; nearest_measured_id: string; nearest_measured_value: number; constraint?: string };
export type Recommendation = Score & { rank: number; smiles: string; selection_reason: string; outside_diagnostic_range: boolean };
export type Round = { round: number; status: string; training_count: number; training_sha256: string; preview_id?: string; recommendations: Recommendation[]; results: Record<string, { status: string; value: number | null }> };
export type Campaign = { id: string; name: string; assay: string; endpoint: string; revision: string; demo: boolean; compounds: Compound[]; rounds: Round[]; events: { sequence: number; at: string; action: string }[] };
export type Preview = { id: string; revision: string; round: number; training_count: number; recommendations: Recommendation[]; scored: Score[] };
export type Job = { id: string; status: string; preview_id?: string; error?: string };
export type CampaignSummary = { id: string; name: string; endpoint: string; counts: Record<string, number>; rounds: { round: number; status: string }[] };
export const base = '/api/backend';
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store' });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Please check the supplied fields and CSV format.');
  return result;
}
