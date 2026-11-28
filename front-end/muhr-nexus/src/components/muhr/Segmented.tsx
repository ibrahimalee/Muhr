import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { gsap, prefersReducedMotion } from "@/lib/motion";

/** A row of options with one clay pill that slides under the chosen one. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: readonly { id: T; label: string; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const first = useRef(true);

  useEffect(() => {
    const place = (animate: boolean) => {
      const btn = wrap.current?.querySelector<HTMLElement>('[aria-pressed="true"]');
      if (!btn || !pill.current) return;
      const vars = { x: btn.offsetLeft, width: btn.offsetWidth };
      if (!animate || prefersReducedMotion()) gsap.set(pill.current, vars);
      else gsap.to(pill.current, { ...vars, duration: 0.45, ease: "power3.inOut" });
    };
    place(!first.current);
    first.current = false;
    const onResize = () => place(false);
    window.addEventListener("resize", onResize);
    void document.fonts?.ready.then(() => place(false));
    return () => window.removeEventListener("resize", onResize);
    // Counts change the button widths, so re-place on those too.
  }, [value, options]);

  return (
    <div ref={wrap} className="relative flex rounded-[8px] border border-rule-strong bg-paper/60 p-0.5" role="group" aria-label={label}>
      <span ref={pill} className="clay absolute bottom-0.5 left-0 top-0.5 rounded-[6px] bg-ink [--clay-shade:var(--ink)]" aria-hidden />
      {options.map((o) => {
        const on = value === o.id;
        return (
          <button
            key={o.id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.id)}
            className={cn(
              "relative z-10 flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 text-xs font-semibold transition-colors duration-300",
              on ? "text-sheet" : "text-graphite hover:text-ink",
            )}
          >
            {o.label}
            {o.count != null ? (
              <span className={cn("num text-2xs font-medium transition-colors duration-300", on ? "text-sheet/70" : "text-graphite/80")}>{o.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
