/** Aster mark: a six-membered ring with radiating petals — part molecule, part flower. */
export function LogoMark({ className }: { className?: string }) {
  const r = 5.2;
  const pts = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    return [12 + r * Math.cos(a), 12 + r * Math.sin(a), Math.cos(a), Math.sin(a)] as const;
  });
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <polygon
        points={pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ")}
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      {pts.map(([x, y, cx, cy], i) => (
        <line
          key={i}
          x1={x + cx * 2.2}
          y1={y + cy * 2.2}
          x2={x + cx * (i % 2 ? 4.2 : 5.6)}
          y2={y + cy * (i % 2 ? 4.2 : 5.6)}
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      ))}
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark className="size-[22px] text-ink" />
      <span className="text-[17px] font-semibold tracking-[-0.02em] text-ink">Aster</span>
    </span>
  );
}
