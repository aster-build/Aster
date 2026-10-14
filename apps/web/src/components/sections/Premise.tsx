"use client";

import { useCallback, useEffect, useRef, type PointerEvent } from "react";
import { Reveal, usePrefersReducedMotion } from "@/components/ui";
import { library, shortlist } from "@/lib/data";

// Similarity-network backdrop: each compound links to its nearest neighbours
// in the schematic chemical space. Computed once at module load.
const W = 1200;
const H = 520;
const nodes = library.map((c) => ({
  x: (c.xy[0] / 100) * W,
  y: (c.xy[1] / 100) * H,
  hl: c.shortlisted,
}));
const edges: [number, number][] = [];
nodes.forEach((a, i) => {
  nodes
    .map((b, j) => ({ j, d: Math.hypot(a.x - b.x, a.y - b.y) }))
    .filter(({ j, d }) => j !== i && d < 150)
    .sort((p, q) => p.d - q.d)
    .slice(0, 3)
    .forEach(({ j }) => {
      if (i < j) edges.push([i, j]);
    });
});

// Pointer interaction, in viewBox units.
const RADIUS = 170; // how far the cursor's influence reaches
const PUSH = 3.2; // repulsion strength
const SPRING = 0.045; // pull back toward each node's home position
const DAMPING = 0.86; // velocity retained per frame
const REST = 0.02; // below this everywhere, the loop stops

/** Lets the cursor push nearby nodes; they spring back when it moves away. */
function useNodeField(enabled: boolean) {
  const svgRef = useRef<SVGSVGElement>(null);
  const circleRefs = useRef<(SVGCircleElement | null)[]>([]);
  const lineRefs = useRef<(SVGLineElement | null)[]>([]);
  const state = useRef(nodes.map((n) => ({ x: n.x, y: n.y, vx: 0, vy: 0 })));
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const kickRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let frame: number | null = null;

    const step = () => {
      const p = pointer.current;
      let moving = false;
      state.current.forEach((s, i) => {
        const home = nodes[i];
        let ax = (home.x - s.x) * SPRING;
        let ay = (home.y - s.y) * SPRING;
        if (p) {
          const dx = s.x - p.x;
          const dy = s.y - p.y;
          const d = Math.hypot(dx, dy);
          if (d < RADIUS && d > 0.001) {
            const f = (1 - d / RADIUS) ** 2 * PUSH;
            ax += (dx / d) * f;
            ay += (dy / d) * f;
          }
        }
        s.vx = (s.vx + ax) * DAMPING;
        s.vy = (s.vy + ay) * DAMPING;
        s.x += s.vx;
        s.y += s.vy;
        if (Math.abs(s.vx) + Math.abs(s.vy) > REST || Math.abs(home.x - s.x) + Math.abs(home.y - s.y) > REST) {
          moving = true;
        }
        const c = circleRefs.current[i];
        if (c) {
          c.setAttribute("cx", s.x.toFixed(2));
          c.setAttribute("cy", s.y.toFixed(2));
        }
      });
      edges.forEach(([a, b], k) => {
        const l = lineRefs.current[k];
        if (!l) return;
        const sa = state.current[a];
        const sb = state.current[b];
        l.setAttribute("x1", sa.x.toFixed(2));
        l.setAttribute("y1", sa.y.toFixed(2));
        l.setAttribute("x2", sb.x.toFixed(2));
        l.setAttribute("y2", sb.y.toFixed(2));
      });
      // Keep running while the cursor is inside or nodes are still settling.
      frame = moving || p ? requestAnimationFrame(step) : null;
    };

    kickRef.current = () => {
      if (frame == null) frame = requestAnimationFrame(step);
    };
    return () => {
      kickRef.current = null;
      if (frame != null) cancelAnimationFrame(frame);
    };
  }, [enabled]);

  const onPointerMove = useCallback((e: PointerEvent) => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm || !kickRef.current) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    pointer.current = { x: pt.x, y: pt.y };
    kickRef.current();
  }, []);

  const onPointerLeave = useCallback(() => {
    pointer.current = null;
    kickRef.current?.(); // let the nodes settle home
  }, []);

  return { svgRef, circleRefs, lineRefs, onPointerMove, onPointerLeave };
}

export function Premise() {
  const reduced = usePrefersReducedMotion();
  const { svgRef, circleRefs, lineRefs, onPointerMove, onPointerLeave } = useNodeField(!reduced);

  return (
    <section
      aria-labelledby="premise-title"
      className="relative overflow-hidden"
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      <svg
        ref={svgRef}
        aria-hidden="true"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid slice"
        className="drift absolute inset-0 h-full w-full [mask-image:radial-gradient(ellipse_52%_48%_at_center,rgb(0_0_0/0.18)_35%,black_80%)]"
      >
        <g stroke="var(--color-line-strong)" strokeWidth={1} opacity={0.9}>
          {edges.map(([i, j], k) => (
            <line
              key={`${i}-${j}`}
              ref={(el) => {
                lineRefs.current[k] = el;
              }}
              x1={nodes[i].x}
              y1={nodes[i].y}
              x2={nodes[j].x}
              y2={nodes[j].y}
            />
          ))}
        </g>
        <g>
          {nodes.map((n, i) => (
            <circle
              key={i}
              ref={(el) => {
                circleRefs.current[i] = el;
              }}
              cx={n.x}
              cy={n.y}
              {...(n.hl
                ? {
                    r: 5,
                    fill: "var(--color-paper)",
                    stroke: "var(--color-accent)",
                    strokeOpacity: 0.45,
                    strokeWidth: 1.5,
                  }
                : { r: 2.4, fill: "#c9cacd" })}
            />
          ))}
        </g>
      </svg>

      <Reveal className="relative mx-auto max-w-[1240px] px-5 py-16 text-center sm:px-8 sm:py-24 lg:py-28">
        <h2
          id="premise-title"
          className="mx-auto max-w-[17ch] text-[clamp(1.9rem,1.05rem+3vw,3.5rem)] leading-[1.05] font-medium tracking-[-0.04em] text-balance text-ink"
        >
          The next experiment should answer{" "}
          <span className="whitespace-nowrap text-[#8a8d93]">a better question.</span>
        </h2>
        <p className="mx-auto mt-6 max-w-[38rem] text-[17px] leading-[1.6] text-ink-2 text-pretty sm:mt-8 sm:text-[19px]">
          A promising prediction is a starting point. Aster explores how activity, uncertainty, and chemical
          diversity can guide what researchers test next.
        </p>
        <p className="mt-8 font-mono text-[11px] text-muted">
          Background: similarity network of the {library.length} illustrative candidates ·{" "}
          {shortlist.length} proposed in round 3
        </p>
      </Reveal>
    </section>
  );
}
