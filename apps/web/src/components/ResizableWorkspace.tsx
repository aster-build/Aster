'use client';

import { Children, useEffect, useState, type CSSProperties, type ReactNode, type PointerEvent } from 'react';

type Layout = { split: number; top: number; table: number };
const defaults: Layout = { split: 59, top: 570, table: 390 };
const bounds = { split: [35, 70], top: [380, 900], table: [180, 750] } as const;
const clamp = (key: keyof Layout, value: number) => Math.max(bounds[key][0], Math.min(bounds[key][1], value));

export function ResizableWorkspace({ children }: { children: ReactNode }) {
  const panels = Children.toArray(children);
  const [layout, setLayout] = useState(defaults);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('aster-panel-layout') || 'null');
      if (saved && Object.keys(defaults).every(key => Number.isFinite(saved[key]))) {
        setLayout({split: clamp('split', saved.split), top: clamp('top', saved.top), table: clamp('table', saved.table)});
      }
    } catch { /* A stale preference should never block the workspace. */ }
  }, []);
  function save(next: Layout) {
    setLayout(next);
    try { localStorage.setItem('aster-panel-layout', JSON.stringify(next)); } catch { /* Storage may be disabled. */ }
  }
  function separator(key: keyof Layout, label: string) {
    const vertical = key === 'split';
    function drag(event: PointerEvent<HTMLDivElement>) {
      if (event.button !== 0) return;
      event.preventDefault();
      const handle = event.currentTarget;
      const initial = {...layout};
      const origin = vertical ? event.clientX : event.clientY;
      const width = handle.parentElement!.getBoundingClientRect().width;
      handle.setPointerCapture(event.pointerId);
      let next = initial;
      const move = (e: globalThis.PointerEvent) => {
        const delta = (vertical ? (e.clientX-origin) / width * 100 : e.clientY-origin);
        next = {...initial, [key]: clamp(key, initial[key] + delta)};
        setLayout(next);
      };
      const end = () => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', end);
        handle.removeEventListener('pointercancel', end);
        save(next);
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', end);
      handle.addEventListener('pointercancel', end);
    }
    return <div role="separator" tabIndex={0} aria-label={label} aria-orientation={vertical ? 'vertical' : 'horizontal'} aria-valuemin={bounds[key][0]} aria-valuemax={bounds[key][1]} aria-valuenow={Math.round(layout[key])} title={`${label} · drag or use arrow keys · double-click to reset`} className={`panel-resizer ${vertical ? 'vertical' : 'horizontal'}`} onPointerDown={drag} onDoubleClick={() => save({...layout, [key]: defaults[key]})} onKeyDown={e => {
      const decrease = vertical ? 'ArrowLeft' : 'ArrowUp';
      const increase = vertical ? 'ArrowRight' : 'ArrowDown';
      if (![decrease,increase,'Home','End'].includes(e.key)) return;
      e.preventDefault();
      const value = e.key === 'Home' ? bounds[key][0] : e.key === 'End' ? bounds[key][1] : layout[key] + (e.key === decrease ? -1 : 1) * (vertical ? 2 : 24);
      save({...layout,[key]:clamp(key,value)});
    }}><span /></div>;
  }
  return <div className="resizable-workspace" style={{'--panel-split':`${layout.split}%`,'--panel-height':`${layout.top}px`,'--table-height':`${layout.table}px`} as CSSProperties}>
    <div className="decision-grid">{panels[0]}{separator('split','Resize landscape and compound widths')}{panels[1]}</div>
    {separator('top','Resize landscape and compound height')}
    {panels[2]}
    {separator('table','Resize proposed batch height')}
    <div className="layout-hint"><span>Drag dividers to resize panels</span><button onClick={() => save(defaults)}>Reset layout</button></div>
  </div>;
}
