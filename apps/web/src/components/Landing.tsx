"use client";

import { useCallback, useRef, useState } from "react";
import { ApproachDialog } from "@/components/ApproachDialog";
import { ArrowDown, ArrowUpRight } from "@/components/icons";
import { Wordmark } from "@/components/Logo";
import { BOOK_DEMO_URL } from "@/lib/site";
import { ProductPreview } from "@/components/ProductPreview";
import { BudgetDemo } from "@/components/sections/BudgetDemo";
import { Closing } from "@/components/sections/Closing";
import { DataWorkflow } from "@/components/sections/DataWorkflow";
import { Evaluation } from "@/components/sections/Evaluation";
import { Inspector } from "@/components/sections/Inspector";
import { Premise } from "@/components/sections/Premise";
import { Workflow } from "@/components/sections/Workflow";

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function Landing() {
  const previewRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [guideVisible, setGuideVisible] = useState(false);

  const explore = useCallback(() => {
    setExpanded(true);
    setGuideVisible(true);
    const el = previewRef.current;
    if (!el) return;
    el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    el.focus({ preventScroll: true });
  }, []);

  const returnFocus = useRef<HTMLElement | null>(null);
  const openApproach = useCallback(() => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.showModal();
  }, []);
  const closeApproach = useCallback(() => dialogRef.current?.close(), []);
  // Runs for every close path (button, Escape, backdrop).
  const restoreFocus = useCallback(() => returnFocus.current?.focus(), []);

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-white"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 bg-paper/85 backdrop-blur-md">
        <nav
          aria-label="Primary"
          className="mx-auto flex h-16 max-w-[1240px] items-center justify-between px-5 sm:px-8"
        >
          <a href="#main" aria-label="Aster, home" className="-m-1 rounded-md p-1">
            <Wordmark />
          </a>
          <div className="flex items-center gap-1 sm:gap-2">
            <a href="/dashboard" className="inline-flex h-9 items-center rounded-md bg-accent px-4 text-[13px] font-medium text-white hover:bg-accent-strong">Open workspace ↗</a>
            <a
              href="#workflow"
              className="hidden h-9 items-center rounded-md px-3 text-[14px] text-ink-2 hover:bg-stage hover:text-ink md:inline-flex"
            >
              Approach
            </a>
            <a
              href="#evaluation"
              className="hidden h-9 items-center rounded-md px-3 text-[14px] text-ink-2 hover:bg-stage hover:text-ink md:inline-flex"
            >
              Evaluation
            </a>
            {/* <button
              type="button"
              onClick={explore}
              className="h-9 rounded-md px-3 text-[14px] text-ink-2 hover:bg-stage hover:text-ink"
            >
              <span className="sm:hidden">Prototype</span>
              <span className="hidden sm:inline">View prototype</span>
            </button> */}
            <a
              href={BOOK_DEMO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex h-9 items-center rounded-md bg-ink px-3.5 text-[14px] font-medium whitespace-nowrap text-white hover:bg-[#2a2c30]"
            >
              Book a demo
              <ArrowUpRight size={13} weight={2.2} className="ml-1 opacity-70" />
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          </div>
        </nav>
      </header>

      <main id="main" tabIndex={-1} className="outline-none">
        <section aria-labelledby="hero-title" className="relative">
          <div className="mx-auto max-w-[1240px] px-5 pt-12 sm:px-8 sm:pt-20 lg:pt-24">
            <div className="max-w-[60rem]">
              <h1
                id="hero-title"
                className="rise text-[clamp(2.5rem,1.1rem+4.4vw,4.625rem)] leading-[0.98] font-medium tracking-[-0.045em] text-balance text-ink"
              >
                Aster makes every experiment count.
              </h1>

              <div className="rise mt-7 sm:mt-9" style={{ animationDelay: "120ms" }}>
                <p className="max-w-[34rem] text-[17px] leading-[1.6] text-ink-2 text-pretty sm:text-[18px]">
                  Prioritize promising compounds, understand prediction uncertainty, and turn each assay
                  into a smarter next experiment.
                </p>
                <div className="mt-7 flex flex-col gap-3 min-[420px]:flex-row min-[420px]:flex-wrap">
                  <button
                    type="button"
                    onClick={explore}
                    className="group inline-flex h-11 items-center justify-center gap-2 rounded-md bg-ink px-5 whitespace-nowrap text-[15px] font-medium text-white hover:bg-[#2a2c30]"
                  >
                    Explore the prototype
                    <ArrowDown size={15} className="motion-safe:transition-transform motion-safe:duration-300 motion-safe:group-hover:translate-y-0.5" />
                  </button>
                  <button
                    type="button"
                    onClick={openApproach}
                    aria-haspopup="dialog"
                    className="inline-flex h-11 items-center justify-center rounded-md border border-line-strong bg-paper px-5 whitespace-nowrap text-[15px] font-medium text-ink hover:border-ink-2/40 hover:bg-stage"
                  >
                    Our approach
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Product stage */}
          <div className="mx-auto max-w-[1240px] px-3 pt-10 pb-0 sm:px-8 sm:pt-14 sm:pb-2">
            <figure className="rise rounded-[14px] border border-line bg-stage p-2 sm:p-5 lg:p-8" style={{ animationDelay: "260ms" }}>
              <ProductPreview
                ref={previewRef}
                expanded={expanded}
                guideVisible={guideVisible}
                onDismissGuide={() => setGuideVisible(false)}
                onExpand={() => setExpanded(true)}
              />
              <figcaption className="flex flex-col gap-1 px-2 pt-4 pb-1 text-[12.5px] leading-relaxed text-muted sm:flex-row sm:gap-3 sm:px-1 sm:pt-5">
                <span className="font-mono text-[11.5px] text-ink-2 sm:pt-px">Fig. 1</span>
                <span className="max-w-[60rem]">
                  A proposed round of experiments: candidates placed by predicted activity and uncertainty, with
                  a shortlist that balances confident picks against informative ones. All compounds, values and
                  rationales are synthetic and do not come from a trained model.
                </span>
              </figcaption>
            </figure>
          </div>
        </section>

        <Premise />
        <Workflow />
        <Inspector />
        <BudgetDemo />
        <DataWorkflow />
        <Evaluation />
        <Closing onExplore={explore} />
      </main>

      <ApproachDialog ref={dialogRef} onRequestClose={closeApproach} onClosed={restoreFocus} />
    </>
  );
}
