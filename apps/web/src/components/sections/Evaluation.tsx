"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "@/components/icons";
import { Eyebrow, Lede, Reveal, SectionTitle, useInView } from "@/components/ui";
import { gridBg } from "@/components/sections/Workflow";

const PROTOCOL = [
  "Curate measurements",
  "Define held-out data",
  "Select a batch",
  "Reveal results",
  "Update",
  "Compare",
];

const PLAN = [
  ["Retrospective first", "Simulate rounds of selection using existing assay measurements before any new experiments."],
  ["Consistent endpoints", "Use one assay endpoint and unit per evaluation so measurements are comparable."],
  ["Hidden until selected", "Measurements stay hidden and are revealed only after a batch has been chosen."],
  ["Separate data", "Keep development data apart from the data used for the final evaluation."],
  ["Baselines and repeats", "Compare against baselines and repeat trials to see how much results vary."],
  ["Training-data overlap", "Where possible, check whether evaluation compounds appear in a pretrained model's training data."],
  ["Prospective validation", "Testing recommendations in new experiments is a future step, not part of the current prototype."],
];

export function Evaluation() {
  const [open, setOpen] = useState(false);
  const [protoRef, protoIn] = useInView<HTMLOListElement>();
  return (
    <section id="evaluation" aria-labelledby="evaluation-title" className="scroll-mt-20">
      <div className="mx-auto max-w-[1240px] px-5 py-14 sm:px-8 sm:py-20 lg:py-24">
        <Reveal className="max-w-[46rem]">
          <Eyebrow>Evaluation plan</Eyebrow>
          <SectionTitle id="evaluation-title" className="mt-4">
            Every recommendation should be testable.
          </SectionTitle>
          <Lede className="mt-5 max-w-[38rem]">
            We’re designing the evaluation around a practical question: how much useful evidence does each round
            of experiments reveal?
          </Lede>
        </Reveal>

        <ul className="mt-10 grid gap-4 sm:mt-12 md:grid-cols-3 lg:gap-6">
          <Panel
            index={0}
            title="Compare against baselines"
            body="Compare selection strategies against random sampling, chemical similarity, and conventional predictive models."
            visual={<BaselinesVisual />}
          />
          <Panel
            index={1}
            title="Test unfamiliar chemistry"
            body="Hold out chemical scaffolds to examine how predictions transfer beyond familiar compounds."
            visual={<ScaffoldVisual />}
          />
          <Panel
            index={2}
            title="Track experimental efficiency"
            body="Measure candidate discovery and predictive performance as additional assay results become available."
            visual={<EfficiencyVisual />}
          />
        </ul>

        {/* Protocol */}
        <Reveal className="mt-10 rounded-[12px] border border-line px-4 py-6 sm:px-6">
          <p className="font-mono text-[11.5px] text-muted">Protocol · one simulated round</p>
          <ol ref={protoRef} className="mt-5 grid gap-y-3 md:grid-cols-6 md:gap-x-0">
            {PROTOCOL.map((step, i) => (
              <li key={step} className="flex items-center gap-3 md:flex-col md:items-start md:gap-3">
                <div className="flex items-center md:w-full">
                  <span
                    style={{ transitionDelay: `${300 + i * 180}ms` }}
                    className={`grid size-7 shrink-0 place-items-center rounded-full border font-mono text-[11px] motion-safe:transition-[transform,opacity] motion-safe:duration-500 motion-safe:ease-[cubic-bezier(0.16,1,0.3,1)] ${
                      i === 3 ? "border-accent bg-accent text-white" : "border-line-strong bg-paper text-ink-2"
                    } ${protoIn ? "" : "motion-safe:scale-50 motion-safe:opacity-0"}`}
                  >
                    {i + 1}
                  </span>
                  {i < PROTOCOL.length - 1 && (
                    <span aria-hidden="true" className="ml-2 hidden h-px flex-1 overflow-hidden bg-line md:mr-2 md:block">
                      <span
                        style={{ transitionDelay: `${420 + i * 180}ms` }}
                        className={`block h-full origin-left bg-line-strong motion-safe:transition-transform motion-safe:duration-500 motion-safe:ease-out ${
                          protoIn ? "" : "motion-safe:scale-x-0"
                        }`}
                      />
                    </span>
                  )}
                </div>
                <span
                  style={{ transitionDelay: `${360 + i * 180}ms` }}
                  className={`text-[14px] text-ink motion-safe:transition-opacity motion-safe:duration-500 md:pr-4 ${protoIn ? "" : "motion-safe:opacity-0"}`}
                >
                  {step}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-5 text-[12.5px] text-muted">
            Step 4 is the key control: results for a batch are only revealed after it has been selected. Steps
            3–5 repeat for several rounds.
          </p>

          <div className="mt-6 border-t border-line pt-5">
            <button
              type="button"
              aria-expanded={open}
              aria-controls="evaluation-plan"
              onClick={() => setOpen((o) => !o)}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line-strong bg-paper px-4 text-[14px] font-medium text-ink hover:bg-stage"
            >
              {open ? "Hide the evaluation plan" : "Read the evaluation plan"}
              <ChevronDown size={14} weight={2.2} className={`motion-safe:transition-transform motion-safe:duration-300 ${open ? "rotate-180" : ""}`} />
            </button>
            <div id="evaluation-plan" hidden={!open} className="fade-swap">
              <dl className="mt-6 grid gap-x-10 border-t border-line md:grid-cols-2">
                {PLAN.map(([t, d]) => (
                  <div key={t} className="grid grid-cols-[10rem_minmax(0,1fr)] gap-x-4 border-b border-line py-3.5 max-sm:grid-cols-1 max-sm:gap-y-1">
                    <dt className="text-[14px] font-medium text-ink">{t}</dt>
                    <dd className="text-[14px] leading-relaxed text-ink-2">{d}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 text-[12.5px] text-muted">
                No evaluation results are shown on this page because none have been produced yet.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Panel({ index, title, body, visual }: { index: number; title: string; body: string; visual: ReactNode }) {
  return (
    <li>
      <Reveal delay={index * 120} className="h-full overflow-hidden rounded-[12px] border border-line">
      <div className={`h-[148px] border-b border-line ${gridBg}`} aria-hidden="true">
        {visual}
      </div>
      <div className="px-5 py-5">
        <h3 className="text-[16px] font-medium text-ink">{title}</h3>
        <p className="mt-1.5 text-[14.5px] leading-relaxed text-muted">{body}</p>
      </div>
      </Reveal>
    </li>
  );
}

function BaselinesVisual() {
  const rows = ["Uncertainty-aware", "Random sampling", "Chemical similarity", "Predictive model only"];
  return (
    <div className="flex h-full flex-col justify-center gap-1 px-5">
      {rows.map((r, i) => (
        <div key={r} className="flex items-center gap-2 rounded-[5px] border border-line bg-paper px-2.5 py-1">
          <span className={`size-1.5 rounded-full ${i === 0 ? "bg-accent" : "bg-faint"}`} />
          <span className="flex-1 font-mono text-[10.5px] text-ink-2">{r}</span>
          <span className="font-mono text-[10px] text-faint">pending</span>
        </div>
      ))}
    </div>
  );
}

function ScaffoldVisual() {
  const cells = Array.from({ length: 18 }, (_, i) => i);
  const held = new Set([4, 5, 10, 11]);
  return (
    <div className="flex h-full items-center justify-center gap-6 px-5">
      <div className="grid grid-cols-6 gap-1.5">
        {cells.map((i) => (
          <span
            key={i}
            className={`size-[18px] rounded-[3px] ${held.has(i) ? "border border-dashed border-accent bg-accent-soft" : "bg-paper ring-1 ring-line-strong"}`}
          />
        ))}
      </div>
      <div className="space-y-1.5 font-mono text-[10.5px]">
        <p className="flex items-center gap-1.5 text-ink-2">
          <span className="size-2.5 rounded-[2px] bg-paper ring-1 ring-line-strong" /> seen scaffolds
        </p>
        <p className="flex items-center gap-1.5 text-accent-strong">
          <span className="size-2.5 rounded-[2px] border border-dashed border-accent bg-accent-soft" /> held out
        </p>
      </div>
    </div>
  );
}

function EfficiencyVisual() {
  return (
    <svg viewBox="0 0 240 148" className="h-full w-full" preserveAspectRatio="xMidYMid meet">
      <line x1="40" y1="28" x2="40" y2="112" stroke="var(--color-line-strong)" />
      <line x1="40" y1="112" x2="212" y2="112" stroke="var(--color-line-strong)" />
      {[1, 2, 3, 4, 5].map((r) => (
        <g key={r}>
          <line x1={40 + r * 33} x2={40 + r * 33} y1="112" y2="116" stroke="var(--color-line-strong)" />
          <text x={40 + r * 33} y="128" textAnchor="middle" fontSize="10" fontFamily="var(--font-geist-mono)" fill="var(--color-muted)">
            {r}
          </text>
        </g>
      ))}
      <text x="126" y="142" textAnchor="middle" fontSize="10" fontFamily="var(--font-geist-mono)" fill="var(--color-muted)">
        assay round
      </text>
      <text x="30" y="70" textAnchor="middle" fontSize="10" fontFamily="var(--font-geist-mono)" fill="var(--color-muted)" transform="rotate(-90 30 70)">
        evidence
      </text>
      <rect x="78" y="56" width="96" height="22" rx="4" fill="var(--color-paper)" stroke="var(--color-line-strong)" strokeDasharray="3 3" />
      <text x="126" y="71" textAnchor="middle" fontSize="10" fontFamily="var(--font-geist-mono)" fill="var(--color-muted)">
        to be measured
      </text>
    </svg>
  );
}
