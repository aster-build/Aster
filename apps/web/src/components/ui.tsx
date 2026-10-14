"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { ArrowRight, ArrowUp } from "@/components/icons";
import { MU_DOMAIN, type Role } from "@/lib/data";

/** Becomes true once the element scrolls into view (used for one-shot reveals). */
export function useInView<T extends Element>(margin = "0px 0px -15% 0px") {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [margin]);
  return [ref, inView] as const;
}

const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const mq = window.matchMedia(REDUCED_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

export function usePrefersReducedMotion() {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_QUERY).matches,
    () => false,
  );
}

/**
 * Fades and lifts its children in when scrolled into view. Under reduced
 * motion the content is simply shown.
 */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const [ref, inView] = useInView<HTMLDivElement>("0px 0px -10% 0px");
  return (
    <div
      ref={ref}
      className={`motion-safe:transition-[opacity,transform,filter] motion-safe:duration-[900ms] motion-safe:ease-[cubic-bezier(0.16,1,0.3,1)] ${
        inView ? "" : "motion-safe:translate-y-4 motion-safe:opacity-0 motion-safe:blur-[2px]"
      } ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

/** Tracks an element's content box size. */
export function useSize<T extends Element>(initial = { w: 640, h: 360 }) {
  const ref = useRef<T>(null);
  const [size, setSize] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setSize({ w: Math.round(r.width), h: Math.round(r.height) });
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ w: Math.round(width), h: Math.round(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[11.5px] font-medium tracking-[0.14em] text-ink-2 uppercase">{children}</p>
  );
}

export function SectionTitle({
  id,
  children,
  className = "",
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      id={id}
      className={`text-[clamp(1.8rem,1.1rem+2.3vw,2.875rem)] leading-[1.04] font-medium tracking-[-0.038em] text-balance text-ink ${className}`}
    >
      {children}
    </h2>
  );
}

export function Lede({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`text-[17px] leading-[1.6] text-muted text-pretty sm:text-[18px] ${className}`}>{children}</p>
  );
}

/** Small status label used to mark illustrative or planned content. */
export function StatusLabel({ children, tone = "amber" }: { children: ReactNode; tone?: "amber" | "violet" }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-paper px-2.5 py-1 font-mono text-[11px] whitespace-nowrap text-ink-2">
      <span
        className={`size-1.5 rounded-full ${tone === "amber" ? "bg-[#c4831d]" : "bg-accent"}`}
        aria-hidden="true"
      />
      {children}
    </span>
  );
}

export function RoleTag({ role }: { role: Role }) {
  const glyph = {
    Exploit: <circle cx="5" cy="5" r="3.5" fill="currentColor" />,
    Explore: <circle cx="5" cy="5" r="3.25" fill="none" stroke="currentColor" strokeWidth="1.3" />,
    Balanced: (
      <>
        <circle cx="5" cy="5" r="3.25" fill="none" stroke="currentColor" strokeWidth="1.3" />
        <path d="M5 1.75 A3.25 3.25 0 0 1 5 8.25 Z" fill="currentColor" />
      </>
    ),
  }[role];
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-ink-2">
      <svg width="10" height="10" aria-hidden="true" className="text-accent">
        {glyph}
      </svg>
      {role}
    </span>
  );
}

export function IntervalBar({
  mu,
  sigma,
  className = "",
  active = false,
  ticks = false,
}: {
  mu: number;
  sigma: number;
  className?: string;
  active?: boolean;
  ticks?: boolean;
}) {
  const pct = (v: number) => ((v - MU_DOMAIN[0]) / (MU_DOMAIN[1] - MU_DOMAIN[0])) * 100;
  const lo = pct(mu - sigma);
  const hi = pct(mu + sigma);
  return (
    <span className={`relative block ${className}`} aria-hidden="true">
      <span className="relative block h-3">
        <span className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
        {ticks &&
          [5, 6, 7, 8].map((t) => (
            <span key={t} className="absolute top-[3px] h-1.5 w-px bg-line-strong" style={{ left: `${pct(t)}%` }} />
          ))}
        <span
          className={`absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full ${active ? "bg-accent/45" : "bg-ink-2/25"}`}
          style={{ left: `${lo}%`, width: `${hi - lo}%` }}
        />
        <span
          className={`absolute top-1/2 size-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full ${active ? "bg-accent" : "bg-ink-2"}`}
          style={{ left: `${pct(mu)}%` }}
        />
      </span>
      {ticks && (
        <span className="relative mt-1 block h-3 font-mono text-[10.5px] text-muted">
          {[5, 6, 7, 8].map((t) => (
            <span key={t} className="absolute -translate-x-1/2" style={{ left: `${pct(t)}%` }}>
              {t}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}


/** Horizontal axis title rendered in HTML over a chart, with an arrow icon. */
export function XAxisTitle({ left, label, hint }: { left: number; label: ReactNode; hint?: ReactNode }) {
  return (
    <div
      className="pointer-events-none absolute bottom-0 flex items-center gap-1.5 font-mono text-[11px] leading-none whitespace-nowrap text-ink-2"
      style={{ left }}
      aria-hidden="true"
    >
      {label}
      <ArrowRight size={11} weight={2.2} className="text-muted" />
      {hint && <span className="text-muted">{hint}</span>}
    </div>
  );
}

/** Vertical axis title, rotated to read bottom-to-top and ending at `top`. */
export function YAxisTitle({ top, label, hint }: { top: number; label: ReactNode; hint?: ReactNode }) {
  return (
    <div
      className="pointer-events-none absolute left-0 flex origin-top-left items-center gap-1.5 font-mono text-[11px] leading-none whitespace-nowrap text-ink-2"
      style={{ top, transform: "rotate(-90deg) translateX(-100%)" }}
      aria-hidden="true"
    >
      {label}
      <ArrowRight size={11} weight={2.2} className="text-muted" />
      {hint && <span className="text-muted">{hint}</span>}
    </div>
  );
}

/** Keyboard key hint, e.g. the arrow keys. */
export function KeyHint({ dir }: { dir: "up" | "down" }) {
  return (
    <kbd className="inline-grid size-[18px] place-items-center rounded-[4px] border border-accent/25 bg-paper align-[-4px] text-accent-strong">
      <ArrowUp size={11} weight={2.2} className={dir === "down" ? "rotate-180" : ""} />
    </kbd>
  );
}
