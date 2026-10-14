"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { ArrowDown, ArrowRight } from "@/components/icons";
import { Molecule } from "@/components/Molecule";
import {
  IntervalBar,
  Lede,
  Reveal,
  SectionTitle,
  useInView,
  usePrefersReducedMotion,
} from "@/components/ui";
import {
  assayed,
  CLUSTERS,
  exampleResults,
  library,
  nextCandidates,
  shortlist,
  type Cluster,
} from "@/lib/data";

/** Faint grid used only inside scientific illustrations. */
export const gridBg =
  "bg-stage [background-image:linear-gradient(var(--color-line)_1px,transparent_1px),linear-gradient(90deg,var(--color-line)_1px,transparent_1px)] [background-size:24px_24px] [background-position:-1px_-1px]";

const EASE = "motion-safe:ease-[cubic-bezier(0.16,1,0.3,1)]";

/** Entrance styles for an element; content is simply shown under reduced motion. */
function enter(inView: boolean, delay: number, hidden = "motion-safe:translate-y-1.5 motion-safe:opacity-0") {
  return {
    className: `motion-safe:transition-[opacity,transform,clip-path] motion-safe:duration-700 ${EASE} ${inView ? "" : hidden}`,
    style: { transitionDelay: `${delay}ms` } as CSSProperties,
  };
}

export function Workflow() {
  return (
    <section id="workflow" aria-labelledby="workflow-title" className="scroll-mt-20">
      <div className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 sm:py-20 lg:py-24">
        <div className="grid gap-6 lg:grid-cols-12 lg:items-end">
          <Reveal className="lg:col-span-7">
            <SectionTitle id="workflow-title">From candidate library to next experiment.</SectionTitle>
          </Reveal>
          <Reveal delay={120} className="lg:col-span-4 lg:col-start-9">
            <Lede className="max-w-[28rem]">
              A simplified view of the proposed loop: Predict, Prioritize, Test, Learn.
            </Lede>
          </Reveal>
        </div>

        <ol className="mt-10 grid gap-x-6 gap-y-14 sm:mt-12 lg:grid-cols-3 lg:gap-x-8">
          <Step
            index={0}
            n="01"
            stage="Predict"
            title="Predict activity."
            body="Estimate activity against a defined target and inspect the uncertainty around each prediction."
            visual={<PredictVisual />}
          />
          <Step
            index={1}
            n="02"
            stage="Prioritize"
            title="Choose an informative batch."
            body="Balance promising candidates with compounds that explore unfamiliar chemistry."
            visual={<ChemSpaceVisual />}
          />
          <Step
            index={2}
            n="03"
            stage={
              <>
                Test <ArrowRight size={11} className="inline-block align-[-1px]" /> Learn
              </>
            }
            title="Learn from each assay."
            body="Bring experimental measurements back into the workflow to inform the next round."
            visual={<LearnVisual />}
          />
        </ol>
      </div>
    </section>
  );
}

function Step({
  index,
  n,
  stage,
  title,
  body,
  visual,
}: {
  index: number;
  n: string;
  stage: ReactNode;
  title: string;
  body: string;
  visual: ReactNode;
}) {
  return (
    <li>
      <Reveal delay={index * 140} className="flex flex-col">
        <div className={`relative aspect-[4/3.3] overflow-hidden rounded-[10px] border border-line ${gridBg}`}>
          {visual}
        </div>
        <p className="mt-6 font-mono text-[11.5px] text-accent">
          {n} <span className="text-muted">· {stage}</span>
        </p>
        <h3 className="mt-2 text-[20px] leading-tight font-medium tracking-[-0.025em] text-ink sm:text-[22px]">
          {title}
        </h3>
        <p className="mt-2 max-w-[26rem] text-[15.5px] leading-relaxed text-muted">{body}</p>
      </Reveal>
    </li>
  );
}

// ---------------------------------------------------------------------------
// 01 · Predict: molecule tiles resolve into a ranked list with ±σ bars
// ---------------------------------------------------------------------------

function PredictVisual() {
  const [ref, inView] = useInView<HTMLDivElement>();
  const ranked = [...shortlist].sort((a, b) => b.mu - a.mu).slice(0, 5);
  return (
    <div ref={ref} className="absolute inset-0 flex items-center gap-3 p-4 sm:gap-4 sm:p-6" aria-hidden="true">
      <div className="grid shrink-0 grid-cols-2 gap-1.5">
        {shortlist.map((c, i) => {
          const e = enter(inView, i * 80, "motion-safe:scale-[0.92] motion-safe:opacity-0");
          return (
            <div
              key={c.id}
              className={`grid size-[52px] place-items-center rounded-[7px] border border-line bg-paper sm:size-[58px] ${e.className} ${inView ? "scan" : ""}`}
              style={{ ...e.style, animationDelay: `${1600 + i * 1000}ms` }}
            >
              <Molecule structure={c.structure} title="" className="h-[42px] w-[48px] text-ink" />
            </div>
          );
        })}
      </div>

      <span {...enter(inView, 520, "motion-safe:-translate-x-2 motion-safe:opacity-0")}>
        <ArrowRight size={15} weight={1.8} className="text-faint" />
      </span>

      <div className="min-w-0 flex-1 overflow-hidden rounded-[7px] border border-line bg-paper">
        <div className="flex justify-between border-b border-line px-2.5 py-1.5 font-mono text-[10px] text-muted">
          <span>ranked</span>
          <span>pIC₅₀ ± σ</span>
        </div>
        {ranked.map((c, i) => {
          const row = enter(inView, 640 + i * 110, "motion-safe:-translate-x-3 motion-safe:opacity-0");
          const bar = enter(inView, 820 + i * 110, "motion-safe:[clip-path:inset(0_100%_0_0)]");
          return (
            <div
              key={c.id}
              style={row.style}
              className={`flex items-center gap-2 border-b border-line px-2.5 py-[7px] last:border-b-0 ${row.className} ${
                i === 0 ? "bg-accent-soft/40" : ""
              }`}
            >
              <span className={`font-mono text-[10.5px] ${i === 0 ? "text-accent-strong" : "text-ink"}`}>
                {c.id.slice(4)}
              </span>
              <span style={bar.style} className={`min-w-0 flex-1 [clip-path:inset(0_0_0_0)] ${bar.className}`}>
                <IntervalBar mu={c.mu} sigma={c.sigma} active={i === 0} />
              </span>
              <span className="font-mono text-[10px] text-muted tabular-nums">{c.mu.toFixed(1)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 02 · Prioritize: schematic chemical space with smooth cluster outlines
// ---------------------------------------------------------------------------

const VB_W = 100;
const VB_H = 82;
const sx = (x: number) => (x / 100) * VB_W;
const sy = (y: number) => (y / 100) * VB_H;
type Pt = [number, number];

const r2 = (v: number) => Math.round(v * 100) / 100;

/**
 * Smooth cluster region: an ellipse aligned to the cluster's principal axes,
 * sized to its spread. Values are rounded so SSR and hydration agree.
 */
function clusterEllipse(points: Pt[]) {
  const n = points.length;
  const mx = points.reduce((s, p) => s + p[0], 0) / n;
  const my = points.reduce((s, p) => s + p[1], 0) / n;
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  for (const [x, y] of points) {
    sxx += (x - mx) ** 2 / n;
    syy += (y - my) ** 2 / n;
    sxy += ((x - mx) * (y - my)) / n;
  }
  const angle = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  const tr = (sxx + syy) / 2;
  const det = Math.sqrt(((sxx - syy) / 2) ** 2 + sxy ** 2);
  const rx = 1.75 * Math.sqrt(tr + det) + 1.6;
  const ry = 1.75 * Math.sqrt(Math.max(tr - det, 0.01)) + 1.6;
  // Label just outside the upper-right of the ellipse.
  const t = -0.95;
  const lx = rx * Math.cos(t);
  const ly = ry * Math.sin(t);
  const px = mx + lx * Math.cos(angle) - ly * Math.sin(angle);
  const py = my + lx * Math.sin(angle) + ly * Math.cos(angle);
  const d = Math.hypot(px - mx, py - my) || 1;
  return {
    cx: r2(mx),
    cy: r2(my),
    rx: r2(rx),
    ry: r2(ry),
    deg: r2((angle * 180) / Math.PI),
    label: [r2(px + ((px - mx) / d) * 2), r2(py + ((py - my) / d) * 2)] as Pt,
  };
}

const regions = CLUSTERS.map((c) => {
  const pts: Pt[] = [
    ...library.filter((x) => x.cluster === c).map((x) => [sx(x.xy[0]), sy(x.xy[1])] as Pt),
    ...assayed.filter((x) => x.cluster === c).map((x) => [sx(x.xy[0]), sy(x.xy[1])] as Pt),
  ];
  return { cluster: c as Cluster, ...clusterEllipse(pts) };
});

const picks = library.filter((c) => c.shortlisted);

function ChemSpaceVisual() {
  const [ref, inView] = useInView<HTMLDivElement>();
  const fade = (delay: number, hidden = "motion-safe:opacity-0") => ({
    className: `motion-safe:transition-[opacity,transform] motion-safe:duration-[900ms] ${EASE} ${inView ? "" : hidden}`,
    style: { transitionDelay: `${delay}ms`, transformBox: "fill-box", transformOrigin: "center" } as CSSProperties,
  });

  return (
    <div ref={ref} className="absolute inset-0" aria-hidden="true">
      <p className="absolute top-3 left-3.5 z-10 rounded-[5px] border border-line bg-paper/95 px-2 py-0.5 font-mono text-[10.5px] text-ink-2">
        Schematic chemical-space view
      </p>
      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid meet">
        {/* Cluster regions */}
        {regions.map((g, i) => (
          <g key={g.cluster} {...fade(i * 70, "motion-safe:scale-[0.8] motion-safe:opacity-0")}>
            <ellipse
              cx={g.cx}
              cy={g.cy}
              rx={g.rx}
              ry={g.ry}
              transform={`rotate(${g.deg} ${g.cx} ${g.cy})`}
              fill="var(--color-paper)"
              fillOpacity={0.7}
              stroke="var(--color-line-strong)"
              strokeWidth={0.2}
            />
          </g>
        ))}
        {regions.map((g, i) => (
          <text
            key={`l-${g.cluster}`}
            {...fade(300 + i * 70)}
            x={g.label[0]}
            y={g.label[1]}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={2.7}
            fontFamily="var(--font-geist-mono)"
            fill="var(--color-muted)"
          >
            {g.cluster}
          </text>
        ))}

        {/* Untested and assayed compounds */}
        <g {...fade(450)}>
          {library
            .filter((c) => !c.shortlisted)
            .map((c) => (
              <circle key={c.id} cx={sx(c.xy[0])} cy={sy(c.xy[1])} r={0.62} fill="#b3b5bb" />
            ))}
          {assayed.map((a) => (
            <rect
              key={a.id}
              x={sx(a.xy[0]) - 0.62}
              y={sy(a.xy[1]) - 0.62}
              width={1.24}
              height={1.24}
              rx={0.15}
              fill="var(--color-ink-2)"
            />
          ))}
        </g>

        {/* Round-3 batch */}
        {picks.map((c, i) => {
          const x = sx(c.xy[0]);
          const y = sy(c.xy[1]);
          return (
            <g key={c.id} {...fade(800 + i * 140, "motion-safe:scale-0 motion-safe:opacity-0")}>
              {inView && (
                <circle
                  cx={x}
                  cy={y}
                  r={1.15}
                  fill="none"
                  stroke="var(--color-accent)"
                  strokeWidth={0.22}
                  className="ripple"
                  style={{ animationDelay: `${1600 + i * 450}ms` }}
                />
              )}
              <circle cx={x} cy={y} r={2.3} fill="var(--color-accent)" fillOpacity={0.1} />
              <circle cx={x} cy={y} r={1.15} fill="var(--color-accent)" stroke="var(--color-paper)" strokeWidth={0.4} />
            </g>
          );
        })}
      </svg>
      <p className="absolute bottom-3 left-3.5 flex items-center gap-1.5 font-mono text-[10px] text-muted">
        <svg width="10" height="10" viewBox="0 0 10 10">
          <circle cx="5" cy="5" r="4.5" fill="var(--color-accent)" fillOpacity="0.12" />
          <circle cx="5" cy="5" r="2.3" fill="var(--color-accent)" />
        </svg>
        round-3 batch spans 6 of 8 clusters
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 03 · Learn: measurements arrive, then the shortlist updates (loops gently)
// ---------------------------------------------------------------------------

const FINAL_PHASE = 4;
const CYCLE = 10; // ticks per loop, including a hold on the final state

function LearnVisual() {
  const [ref, inView] = useInView<HTMLDivElement>();
  const reduced = usePrefersReducedMotion();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!inView || reduced) return;
    const id = window.setInterval(() => setTick((t) => (t + 1) % CYCLE), 850);
    return () => window.clearInterval(id);
  }, [inView, reduced]);

  // 0: waiting · 1–3: each measurement arrives · 4+: model updated, new shortlist
  const phase = reduced ? FINAL_PHASE : Math.min(tick, FINAL_PHASE);

  return (
    <div ref={ref} className="absolute inset-0 flex flex-col justify-center gap-3 p-4 sm:p-6" aria-hidden="true">
      <div className="overflow-hidden rounded-[7px] border border-line bg-paper">
        <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 border-b border-line px-2.5 py-1.5 font-mono text-[10px] text-muted">
          <span>assay results · example values</span>
          <span>pred.</span>
          <span className="w-9 text-right">meas.</span>
        </div>
        {exampleResults.map((r, i) => {
          const shown = phase > i;
          const fresh = phase === i + 1;
          return (
            <div
              key={r.id}
              className={`grid grid-cols-[1fr_auto_auto] items-center gap-x-3 border-b border-line px-2.5 py-[7px] font-mono text-[10.5px] last:border-b-0 motion-safe:transition-colors motion-safe:duration-700 ${
                fresh ? "bg-accent-soft/70" : "bg-paper"
              }`}
            >
              <span className="text-ink">{r.id}</span>
              <span className="text-muted tabular-nums">
                {r.mu.toFixed(1)}±{r.sigma.toFixed(2)}
              </span>
              <span className="relative w-9 text-right tabular-nums">
                <span
                  className={`absolute inset-0 text-faint motion-safe:transition-opacity motion-safe:duration-300 ${shown ? "opacity-0" : ""}`}
                >
                  ···
                </span>
                <span
                  className={`inline-block font-medium text-ink motion-safe:transition-[opacity,transform] motion-safe:duration-500 ${EASE} ${
                    shown ? "" : "translate-y-1 opacity-0"
                  }`}
                >
                  {r.measured.toFixed(1)}
                </span>
              </span>
            </div>
          );
        })}
      </div>

      <p
        className={`flex items-center justify-center gap-1.5 font-mono text-[10px] motion-safe:transition-colors motion-safe:duration-500 ${
          phase >= FINAL_PHASE ? "text-accent-strong" : "text-faint"
        }`}
      >
        <ArrowDown size={11} weight={2} />
        update model · re-rank
      </p>

      <div
        className={`rounded-[7px] border bg-paper motion-safe:transition-[border-color,box-shadow] motion-safe:duration-700 ${
          phase >= FINAL_PHASE ? "border-accent/35 shadow-[0_0_0_3px_rgb(82_54_201/0.06)]" : "border-line"
        }`}
      >
        <div className="border-b border-line px-2.5 py-1.5 font-mono text-[10px] text-accent-strong">
          updated shortlist · round 4
        </div>
        <div className="flex flex-wrap gap-1.5 px-2.5 py-2">
          {nextCandidates.map((c, i) => (
            <span
              key={c.id}
              className={`rounded-[5px] border border-line px-1.5 py-0.5 font-mono text-[10.5px] text-ink-2 motion-safe:transition-[opacity,transform] motion-safe:duration-500 ${EASE} ${
                phase >= FINAL_PHASE ? "" : "translate-y-1 opacity-0"
              }`}
              style={{ transitionDelay: phase >= FINAL_PHASE ? `${i * 120}ms` : "0ms" }}
            >
              {c.id}
            </span>
          ))}
          <span className="px-1 py-0.5 font-mono text-[10.5px] text-faint">…</span>
        </div>
      </div>
    </div>
  );
}
