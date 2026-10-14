"use client";

import { forwardRef } from "react";
import { XMark } from "@/components/icons";

const STEPS = [
  {
    name: "Predict",
    body: "A model estimates each candidate's activity against the target, together with how uncertain that estimate is.",
  },
  {
    name: "Prioritize",
    body: "An acquisition strategy weighs high predicted activity against high uncertainty and batch diversity, and proposes a shortlist with a stated reason for each pick.",
  },
  {
    name: "Test",
    body: "Researchers review the shortlist, apply their own judgement, and run the assays.",
  },
  {
    name: "Learn",
    body: "Assay results are fed back to update the model, so the next round starts from better-informed predictions.",
  },
];

type Props = { onRequestClose: () => void; onClosed: () => void };

export const ApproachDialog = forwardRef<HTMLDialogElement, Props>(function ApproachDialog(
  { onRequestClose, onClosed },
  ref,
) {
  return (
    <dialog
      ref={ref}
      aria-labelledby="approach-title"
      aria-describedby="approach-intro"
      onClose={onClosed}
      onClick={(e) => {
        // Close when the backdrop (the dialog element itself) is clicked.
        if (e.target === e.currentTarget) onRequestClose();
      }}
      className="approach m-auto w-[min(640px,calc(100vw-24px))] max-h-[calc(100dvh-24px)] overflow-y-auto rounded-xl border border-line-strong bg-paper p-0 text-ink shadow-[0_32px_64px_-24px_rgb(17_18_20/0.35)]"
    >
      <div className="px-5 pt-5 pb-6 sm:px-8 sm:pt-7 sm:pb-8">
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="font-mono text-[11px] tracking-[0.12em] text-muted uppercase">Our approach</p>
            <h2 id="approach-title" className="mt-2 text-[24px] leading-tight font-medium tracking-[-0.025em] sm:text-[28px]">
              A loop between models and the bench
            </h2>
          </div>
          <button
            type="button"
            onClick={onRequestClose}
            className="-mt-1 -mr-2 grid size-9 shrink-0 place-items-center rounded-md text-muted hover:bg-stage hover:text-ink"
          >
            <span className="sr-only">Close</span>
            <XMark size={16} />
          </button>
        </div>

        <p id="approach-intro" className="mt-4 text-[15px] leading-relaxed text-ink-2 text-pretty">
          Aster explores how activity predictions and their uncertainty can help researchers choose which
          compounds to test next, and how each round of assay results can make the following choice better.
        </p>

        <ol className="mt-6 border-t border-line">
          {STEPS.map((s, i) => (
            <li key={s.name} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 border-b border-line py-4 sm:grid-cols-[3rem_8rem_minmax(0,1fr)]">
              <span className="font-mono text-[12px] text-accent pt-0.5">0{i + 1}</span>
              <h3 className="text-[15px] font-medium">{s.name}</h3>
              <p className="col-start-2 mt-1 text-[14px] leading-relaxed text-ink-2 sm:col-start-3 sm:mt-0">{s.body}</p>
            </li>
          ))}
        </ol>

        <div className="mt-6 rounded-lg border border-line bg-stage/70 px-4 py-4 sm:px-5">
          <h3 className="flex items-center gap-2 text-[14px] font-medium">
            <span className="size-1.5 rounded-full bg-[#c4831d]" aria-hidden="true" />
            Prototype status
          </h3>
          <ul className="mt-2 space-y-1.5 text-[13.5px] leading-relaxed text-ink-2">
            <li>Aster is an early-stage research prototype. The workflow above is proposed and under development.</li>
            <li>
              The compounds, predictions, uncertainties and rationales on this page are synthetic examples, not
              output from a trained model or a real target.
            </li>
            <li>It has not been validated and makes no claims about performance or clinical use.</li>
          </ul>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onRequestClose}
            className="h-10 rounded-md bg-ink px-4 text-[14px] font-medium text-white hover:bg-[#2a2c30]"
          >
            Done
          </button>
        </div>
      </div>
    </dialog>
  );
});
