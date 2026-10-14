"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { XAxisTitle, YAxisTitle } from "@/components/ui";
import {
  assayedPoints as assayed,
  MU_DOMAIN,
  shortlist,
  SIGMA_DOMAIN,
  untested,
  type Candidate,
} from "@/lib/data";

type Props = {
  selectedId: string;
  onSelect: (id: string) => void;
};

const M = { top: 14, right: 14, bottom: 44, left: 60 };
const UCB_LEVELS = [7.0, 7.5, 8.0];

export function CandidateMap({ selectedId, onSelect }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 640, h: 360 });
  const [hovered, setHovered] = useState<string | null>(null);

  useLayoutEffect(() => {
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

  const { w, h } = size;
  const iw = Math.max(10, w - M.left - M.right);
  const ih = Math.max(10, h - M.top - M.bottom);
  const x = (mu: number) =>
    M.left + ((mu - MU_DOMAIN[0]) / (MU_DOMAIN[1] - MU_DOMAIN[0])) * iw;
  const y = (s: number) =>
    M.top + ih - ((s - SIGMA_DOMAIN[0]) / (SIGMA_DOMAIN[1] - SIGMA_DOMAIN[0])) * ih;

  const xTicks = [5, 6, 7, 8];
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0];
  const selected = shortlist.find((c) => c.id === selectedId) as Candidate;
  const compact = w < 420;
  const showIsoLabels = iw > 470;

  // Isoline of equal upper confidence bound: mu + sigma = level.
  const isoline = (level: number) => {
    const s0 = Math.max(SIGMA_DOMAIN[0], level - MU_DOMAIN[1]);
    const s1 = Math.min(SIGMA_DOMAIN[1], level - MU_DOMAIN[0]);
    return { x1: x(level - s0), y1: y(s0), x2: x(level - s1), y2: y(s1) };
  };

  const sx = x(selected.mu);
  const sy = y(selected.sigma);
  const labelW = 78;
  const labelLeft = sx + 16 + labelW > w - M.right;

  return (
    <div ref={ref} className="relative h-full min-h-[260px] w-full overflow-hidden">
      <svg
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className="absolute inset-0 block select-none"
        aria-hidden="true"
      >
        <defs>
          <clipPath id="plot-clip">
            <rect x={M.left} y={M.top} width={iw} height={ih} />
          </clipPath>
        </defs>

        {/* Grid */}
        <g stroke="var(--color-line)" strokeWidth={1} shapeRendering="crispEdges">
          {xTicks.map((t) => (
            <line key={`gx${t}`} x1={x(t)} x2={x(t)} y1={M.top} y2={M.top + ih} />
          ))}
          {yTicks.map((t) => (
            <line key={`gy${t}`} x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <rect
          x={M.left}
          y={M.top}
          width={iw}
          height={ih}
          fill="none"
          stroke="var(--color-line-strong)"
          shapeRendering="crispEdges"
        />

        {/* Acquisition isolines */}
        <g clipPath="url(#plot-clip)">
          {UCB_LEVELS.map((lvl) => {
            const l = isoline(lvl);
            return (
              <line
                key={lvl}
                {...l}
                stroke="var(--color-accent)"
                strokeOpacity={0.28}
                strokeDasharray="3 4"
              />
            );
          })}
        </g>
        {showIsoLabels &&
          UCB_LEVELS.map((lvl) => {
            const s = Math.min(SIGMA_DOMAIN[1], lvl - MU_DOMAIN[0]) - 0.04;
            return (
              <text
                key={`l${lvl}`}
                x={x(lvl - s) + 5}
                y={y(s) + 4}
                fontSize={10}
                fill="var(--color-accent)"
                fillOpacity={0.75}
                fontFamily="var(--font-geist-mono)"
              >
                μ+σ={lvl.toFixed(1)}
              </text>
            );
          })}

        {/* Untested candidates */}
        <g fill="#b8bac0">
          {untested.map((p, i) => (
            <circle key={i} cx={x(p.mu)} cy={y(p.sigma)} r={compact ? 2.2 : 2.6} />
          ))}
        </g>

        {/* Assayed compounds (rounds 1–2) */}
        <g fill="var(--color-ink-2)">
          {assayed.map((p, i) => (
            <rect key={i} x={x(p.mu) - 2.5} y={y(p.sigma) - 2.5} width={5} height={5} />
          ))}
        </g>

        {/* Selection guides */}
        <g stroke="var(--color-accent)" strokeOpacity={0.45} strokeDasharray="2 3">
          <line x1={sx} x2={sx} y1={sy} y2={M.top + ih} />
          <line x1={M.left} x2={sx} y1={sy} y2={sy} />
        </g>

        {/* Proposed shortlist */}
        {shortlist.map((c) => {
          const cx = x(c.mu);
          const cy = y(c.sigma);
          const isSel = c.id === selectedId;
          const isHover = hovered === c.id;
          return (
            <g
              key={c.id}
              className="cursor-pointer"
              onClick={() => onSelect(c.id)}
              onPointerEnter={() => setHovered(c.id)}
              onPointerLeave={() => setHovered(null)}
            >
              <circle cx={cx} cy={cy} r={16} fill="transparent" />
              {(isSel || isHover) && (
                <circle
                  cx={cx}
                  cy={cy}
                  r={12}
                  fill="var(--color-accent)"
                  fillOpacity={isSel ? 0.12 : 0.08}
                />
              )}
              <circle
                cx={cx}
                cy={cy}
                r={isSel ? 6.5 : 5.5}
                fill={isSel ? "var(--color-accent)" : "var(--color-paper)"}
                stroke="var(--color-accent)"
                strokeWidth={1.75}
                className="motion-safe:transition-[r] motion-safe:duration-200"
              />
              {!isSel && (
                <text
                  x={cx + 9}
                  y={cy - 7}
                  fontSize={10.5}
                  fontFamily="var(--font-geist-mono)"
                  fill="var(--color-accent)"
                  fontWeight={500}
                >
                  {c.rank}
                </text>
              )}
            </g>
          );
        })}

        {/* Selected label */}
        <g
          transform={`translate(${labelLeft ? sx - 14 - labelW : sx + 14}, ${sy - 11})`}
          pointerEvents="none"
        >
          <rect
            width={labelW}
            height={22}
            rx={4}
            fill="var(--color-paper)"
            stroke="var(--color-line-strong)"
          />
          <text
            x={labelW / 2}
            y={15}
            textAnchor="middle"
            fontSize={11}
            fontFamily="var(--font-geist-mono)"
            fill="var(--color-ink)"
            fontWeight={500}
          >
            {selected.id}
          </text>
        </g>

        {/* Axes */}
        <g
          fontSize={11}
          fontFamily="var(--font-geist-mono)"
          fill="var(--color-muted)"
        >
          {xTicks.map((t) => (
            <text key={`tx${t}`} x={x(t)} y={M.top + ih + 16} textAnchor="middle">
              {t.toFixed(1)}
            </text>
          ))}
          {yTicks.map((t) => (
            <text key={`ty${t}`} x={M.left - 8} y={y(t) + 4} textAnchor="end">
              {t.toFixed(2)}
            </text>
          ))}
        </g>
      </svg>
      <XAxisTitle left={M.left} label="Predicted pIC₅₀" hint="more potent" />
      <YAxisTitle top={M.top} label="Uncertainty σ" hint={ih > 230 ? "more informative" : undefined} />
    </div>
  );
}
