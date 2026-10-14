import { ArrowUp } from "@/components/icons";

/** Keyboard key hint, e.g. the arrow keys. */
export function KeyHint({ dir }: { dir: "up" | "down" }) {
  return (
    <kbd className="inline-grid size-[18px] place-items-center rounded-[4px] border border-accent/25 bg-paper align-[-4px] text-accent-strong">
      <ArrowUp size={11} weight={2.2} className={dir === "down" ? "rotate-180" : ""} />
    </kbd>
  );
}
