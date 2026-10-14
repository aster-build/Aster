import molecules from "@/data/molecules.json";

/*
 * Everything in this file is illustrative. The compounds, predictions,
 * uncertainties, clusters and assay values are synthetic and were written to
 * show the shape of a prioritization decision, not the output of a trained
 * model. Units are consistent across the page:
 *   - mu:    predicted pIC50 (−log10 of IC50 in mol/L)
 *   - sigma: one standard deviation of the predictive distribution, in pIC50 units
 */

export type Role = "Exploit" | "Explore" | "Balanced";

export type Atom = { el: string; x: number; y: number; h: number };
export type Bond = { a: number; b: number; order: number; ring?: number[] };
export type Structure = {
  smiles: string;
  atoms: Atom[];
  bonds: Bond[];
  props: { mw: number; clogp: number; tpsa: number; hbd: number; hba: number };
};

/** Schematic chemical clusters. Assignments are synthetic. */
export const CLUSTERS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
export type Cluster = (typeof CLUSTERS)[number];

export type Candidate = {
  id: string;
  rank: number;
  mu: number;
  sigma: number;
  role: Role;
  cluster: Cluster;
  summary: string;
  rationale: string;
  clarify: string;
  analog: { id: string; similarity: number; measured: number };
  structure: Structure;
};

/** Role follows from uncertainty alone, so it is consistent everywhere. */
export function roleFor(sigma: number): Role {
  if (sigma >= 0.7) return "Explore";
  if (sigma <= 0.35) return "Exploit";
  return "Balanced";
}

const structures = molecules as Record<string, Structure>;

const shortlistBase: Omit<Candidate, "rank" | "structure" | "role">[] = [
  {
    id: "AST-0417",
    mu: 7.8,
    sigma: 0.22,
    cluster: "A",
    summary: "Highest predicted activity, tight interval",
    rationale:
      "The strongest prediction among untested candidates, with a narrow interval. It is a close analog of an assayed compound, so the result should confirm whether the series' trend holds.",
    clarify:
      "Whether the series trend extends this far. A result well below its assayed analog would suggest the model is over-extrapolating from close neighbours.",
    analog: { id: "AST-0391", similarity: 0.74, measured: 7.4 },
  },
  {
    id: "AST-1540",
    mu: 7.4,
    sigma: 0.31,
    cluster: "B",
    summary: "Confident prediction, new basic side chain",
    rationale:
      "Adds a basic piperazine that none of the assayed compounds carry, while the prediction stays confident. A useful check of whether the model's confidence transfers to this substitution.",
    clarify:
      "Whether the basic piperazine changes activity in a way the model has not seen among assayed compounds.",
    analog: { id: "AST-0388", similarity: 0.62, measured: 7.0 },
  },
  {
    id: "AST-0786",
    mu: 6.9,
    sigma: 0.78,
    cluster: "C",
    summary: "Sparsely sampled scaffold, high uncertainty",
    rationale:
      "Its quinazoline core is barely represented among assayed compounds, so the model is unsure. Measuring it is expected to reduce uncertainty for many neighbouring candidates at once.",
    clarify:
      "How active this sparsely sampled series really is. One measurement here informs predictions for the rest of its cluster.",
    analog: { id: "AST-0154", similarity: 0.41, measured: 6.1 },
  },
  {
    id: "AST-2051",
    mu: 7.1,
    sigma: 0.55,
    cluster: "D",
    summary: "Good activity estimate, moderate uncertainty",
    rationale:
      "Balances a promising prediction against moderate uncertainty. Structurally it sits between two explored clusters, so either outcome sharpens the map in that region.",
    clarify:
      "Which neighbouring series this compound behaves like, sharpening predictions in the region between them.",
    analog: { id: "AST-0402", similarity: 0.53, measured: 6.8 },
  },
  {
    id: "AST-1182",
    mu: 6.5,
    sigma: 0.92,
    cluster: "E",
    summary: "Small polar fragment, far from tested chemistry",
    rationale:
      "A small, polar compound unlike anything tested so far. Its prediction is the least certain in the batch, which makes the assay informative whether it is active or not.",
    clarify:
      "Whether small polar fragments are worth pursuing at all. Either outcome removes much of the uncertainty in this region.",
    analog: { id: "AST-0067", similarity: 0.33, measured: 5.4 },
  },
  {
    id: "AST-0923",
    mu: 6.7,
    sigma: 0.48,
    cluster: "F",
    summary: "Diversifies the batch with a new bicyclic core",
    rationale:
      "Selected partly for diversity: its bicyclic core differs from the other five picks, so the batch does not spend every assay on one series.",
    clarify:
      "Whether the new bicyclic core is viable, keeping a second option open if the leading series stalls.",
    analog: { id: "AST-0230", similarity: 0.47, measured: 6.3 },
  },
];

export const shortlist: Candidate[] = shortlistBase.map((c, i) => ({
  ...c,
  rank: i + 1,
  role: roleFor(c.sigma),
  structure: structures[c.id],
}));

export const byId = (id: string) => shortlist.find((c) => c.id === id) as Candidate;

// ---------------------------------------------------------------------------
// Synthetic library
// ---------------------------------------------------------------------------

// Deterministic PRNG so server and client render the same points.
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(rand: () => number) {
  const u = 1 - rand();
  const v = rand();
  // Quantized: Math.log/cos can differ in the last bit between Node and the
  // browser, which would otherwise change the data between SSR and hydration.
  return Math.round(Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) * 1e6) / 1e6;
}

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));
const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * Per-cluster parameters. Well-explored series have lower uncertainty; sparse
 * ones (C, E, H) are less certain. `xy` is a schematic chemical-space centre.
 */
const CLUSTER_SPEC: Record<Cluster, { n: number; mu: number; sigma: number; xy: [number, number] }> = {
  A: { n: 22, mu: 6.2, sigma: 0.28, xy: [27, 34] },
  B: { n: 20, mu: 6.0, sigma: 0.34, xy: [44, 63] },
  C: { n: 12, mu: 5.6, sigma: 0.72, xy: [72, 24] },
  D: { n: 18, mu: 5.9, sigma: 0.48, xy: [53, 40] },
  E: { n: 10, mu: 5.3, sigma: 0.82, xy: [83, 70] },
  F: { n: 16, mu: 5.7, sigma: 0.47, xy: [19, 72] },
  G: { n: 18, mu: 5.5, sigma: 0.42, xy: [63, 82] },
  H: { n: 12, mu: 5.2, sigma: 0.62, xy: [88, 44] },
};

export const CLUSTER_CENTERS = Object.fromEntries(
  CLUSTERS.map((c) => [c, CLUSTER_SPEC[c].xy]),
) as Record<Cluster, [number, number]>;

export type LibraryCompound = {
  id: string;
  mu: number;
  sigma: number;
  cluster: Cluster;
  role: Role;
  xy: [number, number]; // schematic chemical-space position, 0–100
  shortlisted: boolean;
};

export type AssayedCompound = {
  id: string;
  measured: number; // illustrative measured pIC50
  sigma: number; // display only: replicate spread, small by construction
  cluster: Cluster;
  round: 1 | 2;
  xy: [number, number];
};

const rand = mulberry32(20261011);
const reserved = new Set<string>([
  ...shortlist.map((c) => c.id),
  ...shortlist.map((c) => c.analog.id),
]);

function newId(lo: number, hi: number) {
  for (;;) {
    const id = `AST-${String(Math.floor(lo + rand() * (hi - lo))).padStart(4, "0")}`;
    if (!reserved.has(id)) {
      reserved.add(id);
      return id;
    }
  }
}

const jitter = (c: Cluster, spread = 5.5): [number, number] => {
  const [x, y] = CLUSTER_SPEC[c].xy;
  return [
    round2(clamp(x + gaussian(rand) * spread, 4, 96)),
    round2(clamp(y + gaussian(rand) * spread, 6, 94)),
  ];
};

/** Untested candidates that were not selected for the round-3 batch. */
export const untested: LibraryCompound[] = CLUSTERS.flatMap((c) => {
  const spec = CLUSTER_SPEC[c];
  return Array.from({ length: spec.n }, () => {
    const sigma = round2(clamp(spec.sigma + gaussian(rand) * 0.13, 0.12, 1.05));
    let mu = round2(clamp(spec.mu + gaussian(rand) * 0.55, 4.6, 7.3));
    // Keep the unselected cloud below the batch's acquisition frontier, so the
    // default selection rule (κ = 1) reproduces the round-3 shortlist.
    if (mu + sigma > 7.1) mu = 7.1 - sigma - rand() * 0.25;
    return {
      id: newId(1000, 2999),
      mu: round2(mu),
      sigma: round2(sigma),
      cluster: c,
      role: roleFor(sigma),
      xy: jitter(c),
      shortlisted: false,
    };
  });
});

const shortlistXY: Record<string, [number, number]> = {
  "AST-0417": [33, 29],
  "AST-1540": [50, 67],
  "AST-0786": [76, 19],
  "AST-2051": [47, 45],
  "AST-1182": [80, 75],
  "AST-0923": [15, 67],
};

/** The full candidate library: unselected candidates plus the round-3 shortlist. */
export const library: LibraryCompound[] = [
  ...shortlist.map((c) => ({
    id: c.id,
    mu: c.mu,
    sigma: c.sigma,
    cluster: c.cluster,
    role: c.role,
    xy: shortlistXY[c.id],
    shortlisted: true,
  })),
  ...untested,
];

/** Compounds measured in rounds 1–2, including each shortlist analog. */
export const assayed: AssayedCompound[] = [
  ...shortlist.map((c) => ({
    id: c.analog.id,
    measured: c.analog.measured,
    sigma: 0.08,
    cluster: c.cluster,
    round: (c.cluster === "C" || c.cluster === "E" ? 2 : 1) as 1 | 2,
    xy: jitter(c.cluster, 3),
  })),
  ...(["A", "A", "A", "A", "A", "B", "B", "B", "D", "D", "D", "F"] as Cluster[]).map(
    (c, i) => ({
      id: newId(100, 999),
      measured: round2(clamp(CLUSTER_SPEC[c].mu + 0.3 + gaussian(rand) * 0.45, 4.9, 7.3)),
      sigma: round2(0.06 + rand() * 0.1),
      cluster: c,
      round: (i % 3 === 0 ? 2 : 1) as 1 | 2,
      xy: jitter(c, 4),
    }),
  ),
];

// Main-map compatibility: assayed compounds are plotted at their measured value.
export const assayedPoints = assayed.map((a) => ({ mu: a.measured, sigma: a.sigma }));

export const ROUND = 3;
export const TOTAL_CANDIDATES = library.length;
export const MU_DOMAIN: [number, number] = [4.5, 8.5];
export const SIGMA_DOMAIN: [number, number] = [0, 1.1];

// ---------------------------------------------------------------------------
// Illustrative selection rule (budget demo)
// ---------------------------------------------------------------------------

export const DIVERSITY_PENALTY = 0.25;

export const PRIORITY_STEPS = [
  { label: "Activity", kappa: 0 },
  { label: "Lean activity", kappa: 0.5 },
  { label: "Balanced", kappa: 1 },
  { label: "Lean exploration", kappa: 2 },
  { label: "Exploration", kappa: 4 },
] as const;

/**
 * Greedy batch selection:
 *   score = predicted pIC50 + κ·σ − 0.25 × (picks already in the same cluster)
 * Deterministic; ties break on compound ID.
 */
export function selectBatch(size: number, kappa: number): LibraryCompound[] {
  const remaining = [...library];
  const counts = new Map<Cluster, number>();
  const picks: LibraryCompound[] = [];
  while (picks.length < size && remaining.length) {
    let best = 0;
    let bestScore = -Infinity;
    remaining.forEach((c, i) => {
      const s = c.mu + kappa * c.sigma - DIVERSITY_PENALTY * (counts.get(c.cluster) ?? 0);
      if (s > bestScore + 1e-9 || (Math.abs(s - bestScore) < 1e-9 && c.id < remaining[best].id)) {
        best = i;
        bestScore = s;
      }
    });
    const [pick] = remaining.splice(best, 1);
    counts.set(pick.cluster, (counts.get(pick.cluster) ?? 0) + 1);
    picks.push(pick);
  }
  return picks;
}

// ---------------------------------------------------------------------------
// Example assay table (data workflow section)
// ---------------------------------------------------------------------------

export type AssayRow = {
  id: string;
  endpoint: string;
  value: number; // IC50 in nM
  unit: "nM";
  pic50: number;
  target: string;
  conditions: string;
  experiment: string;
};

const ic50nM = (p: number) => Math.round(10 ** (9 - p));

export const assayRows: AssayRow[] = shortlist.slice(0, 5).map((c) => {
  const a = assayed.find((x) => x.id === c.analog.id) as AssayedCompound;
  return {
    id: a.id,
    endpoint: "IC50",
    value: ic50nM(a.measured),
    unit: "nM",
    pic50: a.measured,
    target: "TGT-DEMO-1",
    conditions: "Biochemical, 1 mM ATP, 25 °C",
    experiment: `EXP-R${a.round}-${a.round === 1 ? "014" : "027"}`,
  };
});

export function assayRowsToCsv(rows: AssayRow[]) {
  const header = [
    "compound_id",
    "assay_endpoint",
    "value",
    "unit",
    "pIC50",
    "target_id",
    "conditions",
    "experiment_ref",
    "note",
  ];
  const esc = (v: string | number) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    [r.id, r.endpoint, r.value, r.unit, r.pic50.toFixed(2), r.target, r.conditions, r.experiment, "synthetic example data"]
      .map(esc)
      .join(","),
  );
  return [header.join(","), ...lines].join("\n") + "\n";
}

// ---------------------------------------------------------------------------
// "Learn" illustration: example values only, not experimental outcomes
// ---------------------------------------------------------------------------

export const exampleResults = [
  { id: "AST-0417", measured: 7.5 },
  { id: "AST-0786", measured: 6.2 },
  { id: "AST-1182", measured: 5.1 },
].map((r) => ({ ...r, mu: byId(r.id).mu, sigma: byId(r.id).sigma }));

/** Next-ranked candidates under the default rule, used as the "updated shortlist". */
export const nextCandidates = selectBatch(shortlist.length + 3, 1).slice(shortlist.length);
