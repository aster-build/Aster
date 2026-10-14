"use client";

import { forwardRef, useRef, useState, type KeyboardEvent } from "react";
import { CandidateMap } from "@/components/CandidateMap";
import { Molecule } from "@/components/Molecule";
import { LogoMark } from "@/components/Logo";
import { WorkflowSteps } from "@/components/WorkflowSteps";
import { IntervalBar, KeyHint, RoleTag } from "@/components/ui";
import {
  assayed,
  ROUND,
  shortlist,
  TOTAL_CANDIDATES,
  type Candidate,
} from "@/lib/data";

type Props = {
  expanded: boolean;
  guideVisible: boolean;
  onDismissGuide: () => void;
  onExpand: () => void;
};

export const ProductPreview = forwardRef<HTMLDivElement, Props>(
  function ProductPreview({ expanded, guideVisible, onDismissGuide, onExpand }, ref) {
    const [selectedId, setSelectedId] = useState(shortlist[0].id);
    const selected = shortlist.find((c) => c.id === selectedId) as Candidate;
    const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

    const onListKey = (e: KeyboardEvent<HTMLOListElement>) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const i = shortlist.findIndex((c) => c.id === selectedId);
      const visible = expanded ? shortlist.length : rowRefs.current.filter((r) => r?.offsetParent).length;
      const next =
        e.key === "ArrowDown" ? Math.min(visible - 1, i + 1) : Math.max(0, i - 1);
      setSelectedId(shortlist[next].id);
      rowRefs.current[next]?.focus();
    };

    return (
      <div
        ref={ref}
        tabIndex={-1}
        role="region"
        aria-label="Interactive product preview with illustrative data"
        className={`scroll-mt-24 overflow-hidden rounded-[12px] border bg-paper shadow-[0_1px_2px_rgb(17_18_20/0.04),0_24px_48px_-24px_rgb(17_18_20/0.18)] outline-none motion-safe:transition-[border-color,box-shadow] motion-safe:duration-300 ${
          expanded
            ? "border-accent/50 shadow-[0_0_0_4px_rgb(82_54_201/0.08),0_24px_48px_-24px_rgb(17_18_20/0.18)]"
            : "border-line-strong"
        }`}
      >
        {/* Window chrome */}
        <div className="flex h-10 items-center gap-2 border-b border-line bg-paper pr-2 pl-4 sm:h-11 sm:pr-3 sm:pl-5">
          <span aria-hidden="true" className="size-3 rounded-full bg-[#ff5f57] ring-1 ring-black/10 ring-inset" />
          <span aria-hidden="true" className="size-3 rounded-full bg-[#febc2e] ring-1 ring-black/10 ring-inset" />
          <span aria-hidden="true" className="size-3 rounded-full bg-[#28c840] ring-1 ring-black/10 ring-inset" />
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-0.5 font-mono text-[11px] text-ink-2">
            <span className="size-1.5 rounded-full bg-[#c4831d]" aria-hidden="true" />
            Illustrative data
          </span>
        </div>

        {/* Top bar */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2.5 text-[13px] whitespace-nowrap lg:w-[220px]">
            <LogoMark className="size-[18px] shrink-0 text-ink" />
            <span className="font-medium text-ink">Demo campaign</span>
            <span className="text-faint" aria-hidden="true">/</span>
            <span className="text-muted">Round {ROUND}</span>
          </div>

          <div className="order-last w-full lg:order-none lg:flex lg:w-auto lg:flex-1 lg:justify-center"><WorkflowSteps current={1} /></div>
          <span aria-hidden="true" className="hidden lg:block lg:w-[220px]" />
        </div>

        {guideVisible && (
          <div className="fade-swap flex items-start gap-3 border-b border-accent/15 bg-accent-soft/60 px-4 py-2.5 text-[13px] text-ink-2 sm:items-center sm:px-5">
            <p className="flex-1 leading-snug">
              <span className="font-medium text-accent-strong">Interactive preview.</span>{" "}
              Select a candidate on the map or in the shortlist
              <span className="hidden sm:inline">
                {" "}(<KeyHint dir="up" /> <KeyHint dir="down" /> to move through the list)
              </span>. Nothing here is a
              live prediction.
            </p>
            <button
              type="button"
              onClick={onDismissGuide}
              className="-my-1 shrink-0 rounded-[5px] px-2 py-1 text-[12px] font-medium text-accent-strong hover:bg-accent/10"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Map + selected candidate */}
        <div className="grid lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
          <section aria-labelledby="map-title" className="flex flex-col border-b border-line lg:border-r lg:border-b-0">
            <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 pt-4 sm:px-5">
              <h3 id="map-title" className="text-[14px] font-medium text-ink">
                Candidate map
              </h3>
              <p className="font-mono text-[11px] text-muted">
                {TOTAL_CANDIDATES} untested · {assayed.length} assayed
              </p>
            </header>
            <MapLegend />
            <p className="sr-only">
              Scatterplot of candidates by predicted pIC50 and uncertainty. The six proposed compounds sit
              along the upper-right frontier, where predicted activity plus uncertainty is highest. Use the
              shortlist below to select a compound.
            </p>
            <div className="aspect-[1/0.92] px-1 pb-2 sm:aspect-[1/0.62] sm:px-3 lg:aspect-auto lg:flex-1">
              <CandidateMap selectedId={selectedId} onSelect={setSelectedId} />
            </div>
          </section>

          <CandidateDetail candidate={selected} />
        </div>

        {/* Shortlist */}
        <section aria-labelledby="shortlist-title" className="border-t border-line">
          <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 pt-4 pb-3 sm:px-5">
            <h3 id="shortlist-title" className="text-[14px] font-medium text-ink">
              Proposed for round {ROUND}
            </h3>
            <p className="font-mono text-[11px] text-muted">
              Batch of {shortlist.length} · ranked by acquisition with diversity
            </p>
          </header>

          <div
            aria-hidden="true"
            className="hidden grid-cols-[2.25rem_6.5rem_12.5rem_6.5rem_minmax(0,1fr)] gap-x-4 border-y border-line bg-stage/60 px-5 py-2 font-mono text-[11px] text-muted md:grid"
          >
            <span>#</span>
            <span>Compound</span>
            <span>Pred. pIC₅₀ ± σ</span>
            <span>Role</span>
            <span>Rationale</span>
          </div>

          <ol onKeyDown={onListKey} className="border-t border-line md:border-t-0">
            {shortlist.map((c, i) => {
              const isSel = c.id === selectedId;
              const hiddenOnMobile = !expanded && i >= 3;
              return (
                <li key={c.id} className={hiddenOnMobile ? "hidden md:block" : undefined}>
                  <button
                    ref={(el) => {
                      rowRefs.current[i] = el;
                    }}
                    type="button"
                    aria-pressed={isSel}
                    aria-label={`Pick ${c.rank}: ${c.id}, predicted pIC50 ${c.mu.toFixed(1)} plus or minus ${c.sigma.toFixed(2)}, ${c.role}. ${c.summary}.`}
                    onClick={() => setSelectedId(c.id)}
                    className={`relative grid w-full grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line px-4 py-3 text-left last:border-b-0 focus-visible:z-10 focus-visible:rounded-none focus-visible:outline-offset-[-2px] sm:px-5 md:grid-cols-[2.25rem_6.5rem_12.5rem_6.5rem_minmax(0,1fr)] md:gap-x-4 md:py-2.5 ${
                      isSel ? "bg-accent-soft/55" : "hover:bg-stage/70"
                    }`}
                  >
                    {isSel && (
                      <span aria-hidden="true" className="absolute inset-y-0 left-0 w-[2px] bg-accent" />
                    )}
                    <span className={`font-mono text-[12px] ${isSel ? "text-accent-strong" : "text-muted"}`}>
                      {String(c.rank).padStart(2, "0")}
                    </span>
                    <span className="flex min-w-0 flex-col gap-1 md:block">
                      <span className="font-mono text-[13px] font-medium text-ink">{c.id}</span>
                      <span className="md:hidden">
                        <RoleTag role={c.role} />
                      </span>
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="font-mono text-[12.5px] whitespace-nowrap text-ink-2 tabular-nums">
                        {c.mu.toFixed(1)}
                        <span className="text-muted"> ± {c.sigma.toFixed(2)}</span>
                      </span>
                      <IntervalBar mu={c.mu} sigma={c.sigma} className="hidden w-24 md:block" active={isSel} />
                    </span>
                    <span className="hidden md:block">
                      <RoleTag role={c.role} />
                    </span>
                    <span className="hidden truncate text-[13px] text-ink-2 md:block">{c.summary}</span>
                  </button>
                </li>
              );
            })}
          </ol>

          {!expanded && (
            <div className="border-t border-line px-4 py-3 md:hidden">
              <button
                type="button"
                onClick={onExpand}
                className="w-full rounded-[6px] border border-line-strong py-2.5 text-[13px] font-medium text-ink hover:bg-stage"
              >
                Show all {shortlist.length} picks
              </button>
            </div>
          )}
        </section>

        {/* Status bar */}
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-t border-line bg-stage/60 px-4 py-2.5 font-mono text-[11px] text-muted sm:px-5">
          <span>
            Round {ROUND} proposal · {shortlist.length} of {TOTAL_CANDIDATES} candidates
          </span>
          <span>Next: assay the batch, then feed results back</span>
        </div>
      </div>
    );
  },
);

function MapLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 px-4 pt-2.5 pb-1 text-[12px] text-muted sm:px-5">
      <li className="flex items-center gap-1.5">
        <svg width="8" height="8" aria-hidden="true">
          <circle cx="4" cy="4" r="2.75" fill="#b8bac0" />
        </svg>
        Untested
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="8" height="8" aria-hidden="true">
          <rect x="1.5" y="1.5" width="5" height="5" fill="var(--color-ink-2)" />
        </svg>
        Assayed, rounds 1–2
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="12" height="12" aria-hidden="true">
          <circle cx="6" cy="6" r="4.25" fill="white" stroke="var(--color-accent)" strokeWidth="1.6" />
        </svg>
        Proposed
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="16" height="8" aria-hidden="true">
          <line x1="1" y1="7" x2="15" y2="1" stroke="var(--color-accent)" strokeOpacity="0.5" strokeDasharray="3 3" />
        </svg>
        Equal μ + σ
      </li>
    </ul>
  );
}

function CandidateDetail({ candidate: c }: { candidate: Candidate }) {
  return (
    <section aria-labelledby="detail-title" aria-live="polite" className="flex flex-col">
      <header className="flex items-start justify-between gap-4 px-4 pt-4 sm:px-5">
        <div>
          <p className="text-[12px] text-muted">
            Selected · pick {c.rank} of {shortlist.length}
          </p>
          <h3 id="detail-title" className="mt-0.5 font-mono text-[17px] font-medium tracking-tight text-ink">
            {c.id}
          </h3>
        </div>
        <span className="mt-1">
          <RoleTag role={c.role} />
        </span>
      </header>

      <figure key={c.id} className="fade-swap mx-4 mt-3 rounded-[6px] border border-line bg-stage/50 sm:mx-5">
        <Molecule
          structure={c.structure}
          title={`2D structure of ${c.id}`}
          className="mx-auto h-[176px] w-full max-w-[420px] px-2 py-2 text-ink"
        />
        <figcaption className="flex justify-between gap-3 border-t border-line px-3 py-1.5 font-mono text-[10.5px] text-muted">
          <span>MW {c.structure.props.mw}</span>
          <span>cLogP {c.structure.props.clogp}</span>
          <span>TPSA {c.structure.props.tpsa}</span>
        </figcaption>
      </figure>

      <dl className="mx-4 mt-4 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-5 gap-y-3 sm:mx-5">
        <dt className="text-[12px] text-muted">Predicted pIC₅₀</dt>
        <dd className="flex items-center gap-3">
          <span className="font-mono text-[13px] whitespace-nowrap text-ink tabular-nums">
            {c.mu.toFixed(1)} <span className="text-muted">± {c.sigma.toFixed(2)}</span>
          </span>
          <IntervalBar mu={c.mu} sigma={c.sigma} className="min-w-0 flex-1" active ticks />
        </dd>
        <dt className="text-[12px] text-muted">Nearest assayed</dt>
        <dd className="font-mono text-[12px] text-ink-2">
          {c.analog.id} <span className="text-muted">· sim {c.analog.similarity.toFixed(2)} · measured {c.analog.measured.toFixed(1)}</span>
        </dd>
      </dl>

      <div className="mx-4 mt-4 mb-5 border-t border-line pt-3 sm:mx-5">
        <p className="text-[12px] text-muted">Why test it next</p>
        <p key={c.id} className="fade-swap mt-1 text-[13.5px] leading-relaxed text-ink-2 text-pretty">
          {c.rationale}
        </p>
      </div>
    </section>
  );
}
