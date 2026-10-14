"use client";

import { useMemo, useState } from "react";
import { ChevronRight } from "@/components/icons";
import { Lede, Reveal, RoleTag, SectionTitle, useSize, XAxisTitle, YAxisTitle } from "@/components/ui";
import {
  assayedPoints,
  CLUSTERS,
  DIVERSITY_PENALTY,
  library,
  MU_DOMAIN,
  PRIORITY_STEPS,
  selectBatch,
  SIGMA_DOMAIN,
  type LibraryCompound,
  type Role,
} from "@/lib/data";

const MIN_BATCH = 3;
const MAX_BATCH = 12;
const ROLES: Role[] = ["Exploit", "Balanced", "Explore"];

export function BudgetDemo() {
  const [size, setSize] = useState(6);
  const [priority, setPriority] = useState(2);
  const [hovered, setHovered] = useState<string | null>(null);
  const kappa = PRIORITY_STEPS[priority].kappa;
  const batch = useMemo(() => selectBatch(size, kappa), [size, kappa]);
  const clusters = new Set(batch.map((c) => c.cluster));
  const roleCounts = ROLES.map((r) => ({ role: r, n: batch.filter((c) => c.role === r).length }));

  return (
    <section id="budget" aria-labelledby="budget-title" className="scroll-mt-20">
      <div className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 sm:py-20 lg:py-24">
        <div className="grid gap-6 lg:grid-cols-12 lg:items-end">
          <Reveal className="lg:col-span-7">
            <SectionTitle id="budget-title">Fit the experiment to your budget.</SectionTitle>
          </Reveal>
          <Reveal delay={120} className="lg:col-span-4 lg:col-start-9">
            <Lede className="max-w-[28rem]">
              Explore how batch size and selection priorities change the next set of experiments.
            </Lede>
          </Reveal>
        </div>

        <Reveal delay={150}>
        <div className="mt-10 overflow-hidden rounded-[14px] border border-line bg-stage sm:mt-12">
          {/* Controls */}
          <div className="grid gap-6 border-b border-line px-4 py-5 sm:px-6 lg:grid-cols-2 lg:items-start lg:gap-12">
            <div>
              <div className="flex items-baseline justify-between">
                <label htmlFor="batch-size" className="text-[13.5px] font-medium text-ink">
                  Compounds to test
                </label>
                <output htmlFor="batch-size" className="font-mono text-[13px] text-ink tabular-nums">
                  {size}
                </output>
              </div>
              <input
                id="batch-size"
                type="range"
                min={MIN_BATCH}
                max={MAX_BATCH}
                step={1}
                value={size}
                onChange={(e) => setSize(Number(e.target.value))}
                className="mt-3 w-full accent-accent"
              />
              <div className="mt-1 flex justify-between font-mono text-[11px] text-muted">
                <span>{MIN_BATCH}</span>
                <span>{MAX_BATCH}</span>
              </div>
            </div>
            <div>
              <div className="flex items-baseline justify-between">
                <label htmlFor="priority" className="text-[13.5px] font-medium text-ink">
                  Selection priority
                </label>
                <output htmlFor="priority" className="font-mono text-[13px] text-ink">
                  {PRIORITY_STEPS[priority].label}
                </output>
              </div>
              <input
                id="priority"
                type="range"
                min={0}
                max={PRIORITY_STEPS.length - 1}
                step={1}
                value={priority}
                aria-valuetext={`${PRIORITY_STEPS[priority].label}, kappa ${kappa}`}
                onChange={(e) => setPriority(Number(e.target.value))}
                className="mt-3 w-full accent-accent"
              />
              <div className="mt-1 flex justify-between font-mono text-[11px] text-muted">
                <span>Predicted activity</span>
                <span>Exploration</span>
              </div>
            </div>
          </div>

          {/* Outputs */}
          <dl className="grid border-b border-line bg-paper sm:grid-cols-3" aria-live="polite">
            <div className="border-b border-line px-4 py-4 sm:border-r sm:border-b-0 sm:px-6">
              <dt className="text-[12.5px] text-muted">Compounds selected</dt>
              <dd className="mt-1 font-mono text-[26px] leading-tight font-medium text-ink tabular-nums">
                {batch.length}
                <span className="text-[13px] font-normal text-muted"> of {library.length}</span>
              </dd>
            </div>
            <div className="border-b border-line px-4 py-4 sm:border-r sm:border-b-0 sm:px-6">
              <dt className="text-[12.5px] text-muted">Chemical clusters represented</dt>
              <dd className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-2">
                <span className="font-mono text-[26px] leading-tight font-medium text-ink tabular-nums">
                  {clusters.size}
                  <span className="text-[13px] font-normal text-muted"> of {CLUSTERS.length}</span>
                </span>
                <span className="flex gap-1" aria-hidden="true">
                  {CLUSTERS.map((c) => (
                    <span
                      key={c}
                      className={`grid size-[18px] place-items-center rounded-[3px] font-mono text-[10px] ${
                        clusters.has(c) ? "bg-accent text-white" : "border border-line-strong text-faint"
                      }`}
                    >
                      {c}
                    </span>
                  ))}
                </span>
                <span className="sr-only">Clusters: {[...clusters].sort().join(", ")}</span>
              </dd>
            </div>
            <div className="px-4 py-4 sm:px-6">
              <dt className="text-[12.5px] text-muted">Selection rationale</dt>
              <dd className="mt-2">
                <div className="flex h-2 overflow-hidden rounded-full bg-line" aria-hidden="true">
                  {roleCounts.map(({ role, n }) => (
                    <span
                      key={role}
                      className={`h-full motion-safe:transition-[width] motion-safe:duration-300 ${
                        role === "Exploit" ? "bg-accent" : role === "Balanced" ? "bg-accent/55" : "bg-accent/20"
                      }`}
                      style={{ width: `${(n / batch.length) * 100}%` }}
                    />
                  ))}
                </div>
                <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
                  {roleCounts.map(({ role, n }) => (
                    <li key={role} className="flex items-center gap-1.5">
                      <RoleTag role={role} />
                      <span className="font-mono text-[12px] text-ink tabular-nums">{n}</span>
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          </dl>

          {/* Map + synchronized shortlist */}
          <div className="grid bg-paper lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="border-b border-line p-2 sm:p-4 lg:border-r lg:border-b-0">
              <p className="px-2 pt-1 text-[13px] font-medium text-ink">
                Candidate map{" "}
                <span className="font-normal text-muted">· predicted pIC₅₀ vs uncertainty σ</span>
              </p>
              <BatchMap batch={batch} hovered={hovered} />
            </div>
            <div className="flex flex-col">
              <p className="flex items-baseline justify-between border-b border-line px-4 py-3 sm:px-5">
                <span className="text-[13px] font-medium text-ink">Selected batch</span>
                <span className="font-mono text-[11px] text-muted">in pick order</span>
              </p>
              <ol aria-label="Selected batch" className="max-h-[420px] flex-1 overflow-y-auto">
                {batch.map((c, i) => (
                  <li
                    key={c.id}
                    style={{ animationDelay: `${i * 30}ms` }}
                    tabIndex={0}
                    onPointerEnter={() => setHovered(c.id)}
                    onPointerLeave={() => setHovered(null)}
                    onFocus={() => setHovered(c.id)}
                    onBlur={() => setHovered(null)}
                    className={`fade-swap grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line px-4 py-2 last:border-b-0 focus-visible:rounded-none focus-visible:outline-offset-[-2px] sm:grid-cols-[1.75rem_5.5rem_minmax(0,1fr)_auto] sm:px-5 ${
                      hovered === c.id ? "bg-accent-soft/50" : ""
                    }`}
                  >
                    <span className="font-mono text-[11.5px] text-muted">{String(i + 1).padStart(2, "0")}</span>
                    <span className="font-mono text-[12.5px] font-medium text-ink">
                      {c.id}
                      {c.shortlisted && (
                        <span className="ml-1 text-accent" title="In the round-3 shortlist">
                          *
                        </span>
                      )}
                    </span>
                    <span className="hidden font-mono text-[12px] text-ink-2 tabular-nums sm:inline">
                      {c.mu.toFixed(1)} <span className="text-muted">± {c.sigma.toFixed(2)}</span>
                      <span className="ml-2 text-muted">· {c.cluster}</span>
                    </span>
                    <RoleTag role={c.role} />
                  </li>
                ))}
              </ol>
              <p className="border-t border-line px-4 py-2.5 text-[11.5px] text-muted sm:px-5">
                <span className="text-accent">*</span> also in the round-3 shortlist above. Letters are schematic
                clusters.
              </p>
            </div>
          </div>

          <details className="group border-t border-line bg-stage px-4 py-4 sm:px-6">
            <summary className="flex cursor-pointer list-none items-center gap-2 rounded-[4px] text-[13.5px] font-medium text-ink [&::-webkit-details-marker]:hidden">
              <ChevronRight size={13} weight={2.2} className="text-muted motion-safe:transition-transform motion-safe:duration-300 group-open:rotate-90" />
              How this illustrative selection rule works
            </summary>
            <div className="mt-3 grid gap-4 text-[14px] leading-relaxed text-ink-2 lg:grid-cols-2 lg:gap-10">
              <p>
                Picks are made one at a time from the {library.length} synthetic candidates. Each pick takes the
                highest score, then the score of its cluster-mates drops so the batch spreads out. This is a
                transparent, hand-written rule for demonstration. It is not a trained prediction system.
              </p>
              <div>
                <p className="rounded-[6px] border border-line bg-paper px-3 py-2 font-mono text-[12.5px] text-ink">
                  score = μ + κ·σ − {DIVERSITY_PENALTY} × (picks already in cluster)
                </p>
                <p className="mt-2 text-[13px] text-muted">
                  μ: predicted pIC₅₀ · σ: one standard deviation of the prediction · κ: priority setting (
                  {PRIORITY_STEPS.map((s) => s.kappa).join(", ")}). At the defaults (6 compounds, Balanced, κ = 1)
                  the rule reproduces the round-3 shortlist.
                </p>
              </div>
            </div>
          </details>
        </div>
        </Reveal>
      </div>
    </section>
  );
}

function BatchMap({ batch, hovered }: { batch: LibraryCompound[]; hovered: string | null }) {
  const [ref, { w }] = useSize<HTMLDivElement>({ w: 640, h: 340 });
  const h = Math.round(Math.min(380, Math.max(260, w * 0.58)));
  const M = { top: 12, right: 12, bottom: 38, left: 48 };
  const iw = Math.max(10, w - M.left - M.right);
  const ih = h - M.top - M.bottom;
  const x = (mu: number) => M.left + ((mu - MU_DOMAIN[0]) / (MU_DOMAIN[1] - MU_DOMAIN[0])) * iw;
  const y = (s: number) => M.top + ih - ((s - SIGMA_DOMAIN[0]) / (SIGMA_DOMAIN[1] - SIGMA_DOMAIN[0])) * ih;
  const picked = new Map(batch.map((c, i) => [c.id, i + 1]));

  return (
    <div ref={ref} className="relative w-full" style={{ height: h }}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="absolute inset-0 block" role="img"
        aria-label={`Scatterplot of ${library.length} candidates; ${batch.length} selected compounds are highlighted.`}
      >
        <g stroke="var(--color-line)" shapeRendering="crispEdges">
          {[5, 6, 7, 8].map((t) => (
            <line key={t} x1={x(t)} x2={x(t)} y1={M.top} y2={M.top + ih} />
          ))}
          {[0.25, 0.5, 0.75, 1].map((t) => (
            <line key={t} x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <rect x={M.left} y={M.top} width={iw} height={ih} fill="none" stroke="var(--color-line-strong)" shapeRendering="crispEdges" />
        <g fill="var(--color-ink-2)">
          {assayedPoints.map((p, i) => (
            <rect key={i} x={x(p.mu) - 2} y={y(p.sigma) - 2} width={4} height={4} />
          ))}
        </g>
        {/* Selected points last so they sit on top; same keys keep transitions smooth. */}
        {[...library]
          .sort((a, b) => Number(picked.has(a.id)) - Number(picked.has(b.id)))
          .map((c) => {
          const sel = picked.has(c.id);
          const hl = hovered === c.id;
          return (
            <g key={c.id}>
              <circle
                cx={x(c.mu)}
                cy={y(c.sigma)}
                r={hl ? 12 : sel ? 9 : 0}
                fill="var(--color-accent)"
                fillOpacity={hl ? 0.16 : 0.08}
                className="motion-safe:transition-[r,fill-opacity] motion-safe:duration-500 motion-safe:ease-[cubic-bezier(0.16,1,0.3,1)]"
              />
              <circle
                cx={x(c.mu)}
                cy={y(c.sigma)}
                r={sel ? (hl ? 6 : 5) : 2.4}
                fill={sel ? "var(--color-accent)" : "#c3c5ca"}
                stroke="var(--color-paper)"
                strokeWidth={sel ? 1.5 : 0}
                className="motion-safe:transition-[r,fill,stroke-width] motion-safe:duration-500 motion-safe:ease-[cubic-bezier(0.16,1,0.3,1)]"
              />
            </g>
          );
        })}
        <g fontSize={11} fontFamily="var(--font-geist-mono)" fill="var(--color-muted)">
          {[5, 6, 7, 8].map((t) => (
            <text key={t} x={x(t)} y={M.top + ih + 15} textAnchor="middle">
              {t.toFixed(1)}
            </text>
          ))}
          {[0, 0.5, 1].map((t) => (
            <text key={t} x={M.left - 7} y={y(t) + 4} textAnchor="end">
              {t.toFixed(1)}
            </text>
          ))}
        </g>
      </svg>
      <XAxisTitle left={M.left} label="Predicted pIC₅₀" />
      <YAxisTitle top={M.top} label="Uncertainty σ" />
    </div>
  );
}
