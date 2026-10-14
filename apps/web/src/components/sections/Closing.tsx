import { ArrowUp, ArrowUpRight } from "@/components/icons";
import { Reveal } from "@/components/ui";
import { BOOK_DEMO_URL } from "@/lib/site";

export function Closing({ onExplore }: { onExplore: () => void }) {
  return (
    <section aria-labelledby="closing-title">
        <Reveal className="mx-auto max-w-[1240px] px-5 py-16 text-center sm:px-8 sm:py-24 lg:py-28">
          <h2
            id="closing-title"
            className="text-[clamp(2rem,1.15rem+3.2vw,3.75rem)] leading-[1.03] font-medium tracking-[-0.042em] text-balance text-ink"
          >
            What would you test next?
          </h2>
          <p className="mx-auto mt-5 max-w-[30rem] text-[17px] leading-[1.6] text-muted text-pretty sm:text-[18px]">
            Explore the prototype or help shape Aster around a real research workflow.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 min-[420px]:flex-row">
          <button
            type="button"
            onClick={onExplore}
            className="group inline-flex h-11 items-center justify-center gap-2 rounded-md bg-ink px-5 text-[15px] font-medium whitespace-nowrap text-white hover:bg-[#2a2c30]"
          >
            Explore the prototype
            <ArrowUp size={15} className="motion-safe:transition-transform motion-safe:duration-300 motion-safe:group-hover:-translate-y-0.5" />
          </button>
          <a
            href={BOOK_DEMO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-11 items-center justify-center rounded-md border border-line-strong bg-paper px-5 text-[15px] font-medium whitespace-nowrap text-ink hover:border-ink-2/40 hover:bg-stage"
          >
            Book a demo
            <ArrowUpRight size={14} className="ml-1.5 text-muted" />
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
          </div>
        </Reveal>
    </section>
  );
}
