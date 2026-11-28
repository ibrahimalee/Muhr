import { useRef } from "react";
import { cn } from "@/lib/utils";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/motion";

/** A section heading whose words rise into place the first time it scrolls into view. */
export function SectionTitle({ title, kicker, children, className }: { title: string; kicker?: string; children?: React.ReactNode; className?: string }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      if (!root.current || prefersReducedMotion()) return;
      const words = root.current.querySelectorAll("[data-w]");
      gsap.from(words, {
        yPercent: 110,
        rotate: 4,
        duration: 1,
        ease: "power4.out",
        stagger: 0.05,
        scrollTrigger: { trigger: root.current, start: "top 85%", once: true },
      });
      gsap.from(root.current.querySelectorAll("[data-sub]"), {
        y: 14,
        autoAlpha: 0,
        duration: 0.8,
        ease: "power3.out",
        delay: 0.25,
        scrollTrigger: { trigger: root.current, start: "top 85%", once: true },
      });
    },
    { scope: root },
  );
  return (
    <div ref={root} className={cn("flex flex-wrap items-end justify-between gap-x-10 gap-y-3", className)}>
      <div>
        {kicker ? (
          <div data-sub className="mb-3 text-sm font-semibold text-seal">
            {kicker}
          </div>
        ) : null}
        <h2 className="type-wide max-w-[20ch] text-[1.9rem] font-extrabold leading-[1.02] tracking-[-0.015em] sm:text-[2.4rem]" aria-label={title}>
          {title.split(" ").map((w, i) => [
            i ? " " : null,
            <span key={i} aria-hidden className="inline-block overflow-hidden pb-[0.1em] align-bottom">
              <span data-w className="inline-block">
                {w}
              </span>
            </span>,
          ])}
        </h2>
      </div>
      {children ? (
        <div data-sub className="max-w-[46ch] text-sm leading-relaxed text-ink-soft">
          {children}
        </div>
      ) : null}
    </div>
  );
}
