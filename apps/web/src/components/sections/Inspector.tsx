"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Molecule } from "@/components/Molecule";
import { Eyebrow, Lede, Reveal, RoleTag, SectionTitle, StatusLabel, useSize } from "@/components/ui";
import { byId, MU_DOMAIN, type Candidate } from "@/lib/data";

// One candidate per selection motive, all taken from the round-3 shortlist.
const CHOICES = [
  { id: "AST-0417", motive: "Activity-led" },
  { id: "AST-2051", motive: "Balanced" },
  { id: "AST-0786", motive: "Exploration-led" },
] as const;

export function Inspector() {
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const c = byId(CHOICES[active].id);

  const onKey = (e: KeyboardEvent) => {
    const keys: Record<string, number> = {
      ArrowRight: (active + 1) % CHOICES.length,
      ArrowDown: (active + 1) % CHOICES.length,
      ArrowLeft: (active + CHOICES.length - 1) % CHOICES.length,
      ArrowUp: (active + CHOICES.length - 1) % CHOICES.length,
      Home: 0,
      End: CHOICES.length - 1,
    };
    if (!(e.key in keys)) return;
    e.preventDefault();
    setActive(keys[e.key]);
    tabs.current[keys[e.key]]?.focus();
  };

  return (
    <section id="inspector" aria-labelledby="inspector-title" className="scroll-mt-20">
      <div className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 sm:py-20 lg:py-24">
        <Reveal className="max-w-[44rem]">
          <Eyebrow>Inside the shortlist</Eyebrow>
          <SectionTitle id="inspector-title" className="mt-4">
            Why this compound?
          </SectionTitle>
          <Lede className="mt-5 max-w-[36rem]">
            Explore why a candidate was selected, what supports the prediction, and where another experiment
            could help.
          </Lede>
        </Reveal>

        <div className="mt-10 grid grid-cols-1 gap-8 sm:mt-12 lg:grid-cols-12 lg:gap-12">
          {/* Inspector */}
          <Reveal delay={100} className="min-w-0 lg:col-span-6">
            <div className="overflow-hidden rounded-[12px] border border-line bg-stage">
              <div
                role="tablist"
                aria-label="Example candidates"
                onKeyDown={onKey}
                className="grid grid-cols-3 border-b border-line bg-paper"
              >
                {CHOICES.map((ch, i) => {
                  const sel = i === active;
                  return (
                    <button
                      key={ch.id}
                      ref={(el) => {
                        tabs.current[i] = el;
                      }}
                      role="tab"
                      id={`insp-tab-${i}`}
                      aria-selected={sel}
                      aria-controls="insp-panel"
                      tabIndex={sel ? 0 : -1}
                      onClick={() => setActive(i)}
                      className={`relative flex flex-col items-start gap-1 border-r border-line px-3 py-3 text-left last:border-r-0 focus-visible:rounded-none focus-visible:outline-offset-[-2px] sm:px-4 ${
                        sel ? "bg-paper" : "bg-stage/60 hover:bg-stage"
                      }`}
                    >
                      {sel && <span aria-hidden="true" className="absolute inset-x-0 top-0 h-[2px] bg-accent" />}
                      <span className={`font-mono text-[12.5px] font-medium ${sel ? "text-ink" : "text-ink-2"}`}>
                        {ch.id}
                      </span>
                      <span className="text-[11.5px] text-muted">{ch.motive}</span>
                    </button>
                  );
                })}
              </div>

              <div className="relative px-4 pt-4 pb-5 sm:px-6 sm:pt-5">
                <div className="flex items-center justify-between gap-3">
                  <StatusLabel>Illustrative example</StatusLabel>
                  <RoleTag role={c.role} />
                </div>
                <figure key={c.id} className="fade-swap mt-4 rounded-[8px] border border-line bg-paper">
                  <Molecule
                    structure={c.structure}
                    title={`2D structure of ${c.id}`}
                    className="mx-auto h-[200px] w-full max-w-[460px] px-4 py-4 text-ink sm:h-[240px]"
                  />
                  <figcaption className="flex flex-wrap justify-between gap-x-4 gap-y-1 border-t border-line px-4 py-2 font-mono text-[11px] text-muted">
                    <span className="text-ink-2">{c.id}</span>
                    <span>MW {c.structure.props.mw}</span>
                    <span>cLogP {c.structure.props.clogp}</span>
                    <span>TPSA {c.structure.props.tpsa}</span>
                    <span>cluster {c.cluster}</span>
                  </figcaption>
                </figure>
              </div>
            </div>
          </Reveal>

          {/* Evidence */}
          <div
            id="insp-panel"
            role="tabpanel"
            aria-labelledby={`insp-tab-${active}`}
            className="min-w-0 lg:col-span-6 lg:pt-1"
          >
            <Reveal delay={220}>
              <Evidence key={c.id} c={c} />
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

function Evidence({ c }: { c: Candidate }) {
  const ic50 = Math.round(10 ** (9 - c.analog.measured));
  return (
    <div className="fade-swap">
      <div className="grid grid-cols-2 gap-x-6 border-b border-line pb-6">
        <div>
          <p className="text-[12.5px] text-muted">Predicted pIC₅₀</p>
          <p className="mt-1 font-mono text-[32px] leading-none font-medium tracking-tight text-ink tabular-nums">
            {c.mu.toFixed(1)}
          </p>
          <p className="mt-2 text-[12.5px] text-muted">Model estimate · untested</p>
        </div>
        <div>
          <p className="text-[12.5px] text-muted">Uncertainty σ</p>
          <p className="mt-1 font-mono text-[32px] leading-none font-medium tracking-tight text-ink-2 tabular-nums">
            ±{c.sigma.toFixed(2)}
          </p>
          <p className="mt-2 text-[12.5px] text-muted">1 standard deviation, pIC₅₀ units</p>
        </div>
      </div>

      <Distribution c={c} />

      <dl className="grid gap-x-6 gap-y-1 border-y border-line py-5 sm:grid-cols-[9rem_minmax(0,1fr)]">
        <dt className="text-[12.5px] text-muted">Nearest assayed</dt>
        <dd className="text-[14px] text-ink-2">
          <span className="font-mono text-ink">{c.analog.id}</span>
          <span className="text-muted"> · similarity {c.analog.similarity.toFixed(2)}</span>
          <br />
          Measured pIC₅₀ <span className="font-mono text-ink">{c.analog.measured.toFixed(1)}</span>{" "}
          <span className="text-muted">
            (IC₅₀ ≈ {ic50.toLocaleString("en-US")} nM) · illustrative measurement
          </span>
        </dd>
      </dl>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <div>
          <h3 className="text-[14px] font-medium text-ink">Why it was selected</h3>
          <p className="mt-2 text-[14.5px] leading-relaxed text-ink-2 text-pretty">{c.rationale}</p>
        </div>
        <div>
          <h3 className="text-[14px] font-medium text-ink">What testing could clarify</h3>
          <p className="mt-2 text-[14.5px] leading-relaxed text-ink-2 text-pretty">{c.clarify}</p>
        </div>
      </div>
    </div>
  );
}

/** Predictive distribution N(μ, σ²) with the ±1σ band, plus the analog's measurement. */
function Distribution({ c }: { c: Candidate }) {
  const [ref, { w }] = useSize<HTMLDivElement>({ w: 520, h: 150 });
  const h = 150;
  const m = { l: 8, r: 8, t: 14, b: 26 };
  const iw = Math.max(10, w - m.l - m.r);
  const x = (v: number) => m.l + ((v - MU_DOMAIN[0]) / (MU_DOMAIN[1] - MU_DOMAIN[0])) * iw;
  const pdf = (v: number) => Math.exp(-0.5 * ((v - c.mu) / c.sigma) ** 2);
  const yBase = h - m.b;
  const amp = h - m.t - m.b - 10;
  const pts: string[] = [];
  for (let i = 0; i <= 160; i++) {
    const v = MU_DOMAIN[0] + ((MU_DOMAIN[1] - MU_DOMAIN[0]) * i) / 160;
    pts.push(`${x(v).toFixed(1)},${(yBase - pdf(v) * amp).toFixed(1)}`);
  }
  const band: string[] = [];
  for (let i = 0; i <= 40; i++) {
    const v = c.mu - c.sigma + (2 * c.sigma * i) / 40;
    band.push(`${x(v).toFixed(1)},${(yBase - pdf(v) * amp).toFixed(1)}`);
  }
  const ax = x(c.analog.measured);
  const labelRight = ax < m.l + iw * 0.7;

  return (
    <figure className="py-5">
      <div ref={ref} className="w-full min-w-0 overflow-hidden">
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="block" role="img"
          aria-label={`Predicted distribution for ${c.id}: mean ${c.mu.toFixed(1)}, standard deviation ${c.sigma.toFixed(2)}. Nearest assayed analog ${c.analog.id} measured ${c.analog.measured.toFixed(1)}.`}
        >
          {[5, 6, 7, 8].map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={m.t} y2={yBase} stroke="var(--color-line)" />
              <text x={x(t)} y={h - 8} textAnchor="middle" fontSize={11} fontFamily="var(--font-geist-mono)" fill="var(--color-muted)">
                {t.toFixed(1)}
              </text>
            </g>
          ))}
          <line x1={m.l} x2={m.l + iw} y1={yBase} y2={yBase} stroke="var(--color-line-strong)" />
          <polygon
            points={`${x(c.mu - c.sigma)},${yBase} ${band.join(" ")} ${x(c.mu + c.sigma)},${yBase}`}
            fill="var(--color-accent)"
            fillOpacity={0.12}
          />
          <polyline points={pts.join(" ")} fill="none" stroke="var(--color-accent)" strokeWidth={1.75} />
          <line x1={x(c.mu)} x2={x(c.mu)} y1={yBase} y2={yBase - amp} stroke="var(--color-accent)" strokeDasharray="2 3" />
          {/* Measured analog */}
          <g transform={`translate(${ax}, ${yBase})`}>
            <line y1={0} y2={-amp * 0.55} stroke="var(--color-ink)" strokeWidth={1} />
            <rect x={-4.5} y={-amp * 0.55 - 4.5} width={9} height={9} transform={`rotate(45 0 ${-amp * 0.55})`} fill="var(--color-ink)" />
            <text
              x={labelRight ? 9 : -9}
              y={-amp * 0.55 + 4}
              textAnchor={labelRight ? "start" : "end"}
              fontSize={11}
              fontFamily="var(--font-geist-mono)"
              fill="var(--color-ink-2)"
            >
              {c.analog.id}
            </text>
          </g>
        </svg>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[12px] text-muted">
        <span className="flex items-center gap-1.5">
          <svg width="18" height="10" aria-hidden="true">
            <rect x="0" y="2" width="18" height="8" fill="var(--color-accent)" fillOpacity="0.15" />
            <path d="M0 9 Q9 -3 18 9" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
          </svg>
          Prediction: mean, shaded ±1σ
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden="true">
            <rect x="2" y="2" width="6" height="6" transform="rotate(45 5 5)" fill="var(--color-ink)" />
          </svg>
          Measured value of nearest assayed analog (illustrative)
        </span>
        <span>x-axis: pIC₅₀</span>
      </figcaption>
    </figure>
  );
}
