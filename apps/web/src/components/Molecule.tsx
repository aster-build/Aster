import type { Structure } from "@/lib/data";

type Props = {
  structure: Structure;
  title: string;
  className?: string;
};

/**
 * Skeletal 2D structure drawn from precomputed RDKit coordinates
 * (see scripts/gen-molecules.mjs). Carbons are implicit; heteroatoms are
 * labelled with their attached hydrogens, journal style.
 */
export function Molecule({ structure, title, className }: Props) {
  const { atoms, bonds } = structure;
  const first = bonds[0];
  const L = Math.hypot(
    atoms[first.a].x - atoms[first.b].x,
    atoms[first.a].y - atoms[first.b].y,
  );

  const pad = L * 0.75;
  const xs = atoms.map((a) => a.x);
  const ys = atoms.map((a) => a.y);
  const minX = Math.min(...xs) - pad;
  const minY = Math.min(...ys) - pad;
  const w = Math.max(...xs) - Math.min(...xs) + pad * 2;
  const h = Math.max(...ys) - Math.min(...ys) + pad * 2;

  const labelled = (i: number) => atoms[i].el !== "C";
  const stroke = L * 0.055;
  const font = L * 0.5;

  const lines: React.ReactNode[] = [];

  bonds.forEach((bond, i) => {
    const A = atoms[bond.a];
    const B = atoms[bond.b];
    const dx = B.x - A.x;
    const dy = B.y - A.y;
    const len = Math.hypot(dx, dy);
    const ux = dx / len;
    const uy = dy / len;
    // Trim bond ends that meet an atom label.
    const ta = labelled(bond.a) ? L * 0.3 : 0;
    const tb = labelled(bond.b) ? L * 0.3 : 0;
    const x1 = A.x + ux * ta;
    const y1 = A.y + uy * ta;
    const x2 = B.x - ux * tb;
    const y2 = B.y - uy * tb;
    const nx = -uy;
    const ny = ux;

    const seg = (key: string, ax: number, ay: number, bx: number, by: number) => (
      <line key={key} x1={ax} y1={ay} x2={bx} y2={by} />
    );

    if (bond.order === 1) {
      lines.push(seg(`b${i}`, x1, y1, x2, y2));
    } else if (bond.order === 2 && bond.ring) {
      // Main line plus a shortened inner line toward the ring centre.
      const [cx, cy] = bond.ring;
      const side = Math.sign((cx - A.x) * nx + (cy - A.y) * ny) || 1;
      const off = L * 0.16 * side;
      const inset = L * 0.15;
      lines.push(seg(`b${i}`, x1, y1, x2, y2));
      lines.push(
        seg(
          `b${i}i`,
          A.x + ux * Math.max(inset, ta) + nx * off,
          A.y + uy * Math.max(inset, ta) + ny * off,
          B.x - ux * Math.max(inset, tb) + nx * off,
          B.y - uy * Math.max(inset, tb) + ny * off,
        ),
      );
    } else {
      const n = bond.order;
      const gap = L * 0.13;
      for (let k = 0; k < n; k++) {
        const o = (k - (n - 1) / 2) * gap;
        lines.push(seg(`b${i}-${k}`, x1 + nx * o, y1 + ny * o, x2 + nx * o, y2 + ny * o));
      }
    }
  });

  return (
    <svg
      viewBox={`${minX} ${minY} ${w} ${h}`}
      className={className}
      role="img"
      aria-label={title}
      preserveAspectRatio="xMidYMid meet"
    >
      <g
        stroke="currentColor"
        strokeWidth={stroke}
        strokeLinecap="round"
        fill="none"
      >
        {lines}
      </g>
      <g
        fill="currentColor"
        fontSize={font}
        fontFamily="var(--font-geist-sans), sans-serif"
        fontWeight={500}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {atoms.map((atom, i) => {
          if (atom.el === "C") return null;
          if (atom.h === 0) {
            return (
              <text key={i} x={atom.x} y={atom.y}>
                {atom.el}
              </text>
            );
          }
          // Put the H on whichever side has no bonds.
          const meanDx = bonds.reduce((s, b) => {
            if (b.a === i) return s + atoms[b.b].x - atom.x;
            if (b.b === i) return s + atoms[b.a].x - atom.x;
            return s;
          }, 0);
          const half = (atom.el.length > 1 ? 0.85 : 0.64) * font * 0.5;
          const hLeft = meanDx > 0.2 * L;
          const sub =
            atom.h > 1 ? (
              <tspan fontSize={font * 0.62} dy={font * 0.25}>
                {atom.h}
              </tspan>
            ) : null;
          return hLeft ? (
            <text key={i} x={atom.x + half} y={atom.y} textAnchor="end">
              H{sub}
              <tspan dy={sub ? -font * 0.25 : 0}>{atom.el}</tspan>
            </text>
          ) : (
            <text key={i} x={atom.x - half} y={atom.y} textAnchor="start">
              {atom.el}H{sub}
            </text>
          );
        })}
      </g>
    </svg>
  );
}
