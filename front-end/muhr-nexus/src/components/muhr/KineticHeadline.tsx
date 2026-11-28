import { useRef } from "react";
import { cn } from "@/lib/utils";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/motion";

/**
 * Kinetic headline. On arrival, each word rises out of its own mask. Under a mouse,
 * letters near the pointer lift in a small wave (transforms only, so lines never reflow).
 */
export function KineticHeadline({
  text,
  as: Tag = "h1",
  className,
  interactive = true,
}: {
  text: string;
  as?: "h1" | "h2";
  className?: string;
  interactive?: boolean;
}) {
  const root = useRef<HTMLHeadingElement>(null);
  const words = text.split(" ");

  useGSAP(
    () => {
      const el = root.current;
      if (!el || prefersReducedMotion()) return;
      const inner = el.querySelectorAll<HTMLElement>("[data-word-inner]");
      gsap.from(inner, { yPercent: 115, rotate: 6, duration: 1, ease: "power4.out", stagger: 0.07, delay: 0.05 });

      if (!interactive || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
      const letters = Array.from(el.querySelectorAll<HTMLElement>("[data-letter]"));
      const setters = letters.map((l) => ({
        el: l,
        y: gsap.quickTo(l, "y", { duration: 0.5, ease: "power3.out" }),
        r: gsap.quickTo(l, "rotate", { duration: 0.5, ease: "power3.out" }),
      }));
      const move = (e: PointerEvent) => {
        for (const s of setters) {
          const b = s.el.getBoundingClientRect();
          const dx = e.clientX - (b.left + b.width / 2);
          const dy = e.clientY - (b.top + b.height / 2);
          const d = Math.hypot(dx, dy);
          const k = Math.max(0, 1 - d / 140);
          s.y(-k * k * 10);
          s.r(k * k * (dx > 0 ? -6 : 6));
        }
      };
      const leave = () => setters.forEach((s) => (s.y(0), s.r(0)));
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerleave", leave);
      return () => {
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerleave", leave);
      };
    },
    { scope: root, dependencies: [text] },
  );

  return (
    <Tag ref={root} className={cn("type-wide", className)} aria-label={text}>
      {words.map((w, i) => [
        i > 0 ? " " : null,
        <span key={`${w}-${i}`} aria-hidden className="inline-block overflow-hidden pb-[0.08em] align-bottom">
          <span data-word-inner className="inline-block will-change-transform">
            {Array.from(w).map((ch, j) => (
              <span key={j} data-letter className="inline-block">
                {ch}
              </span>
            ))}
          </span>
        </span>,
      ])}
    </Tag>
  );
}
