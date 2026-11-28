import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { gsap, prefersReducedMotion, ScrollTrigger, useGSAP } from "@/lib/motion";

/** A number that counts to its value when it first scrolls into view, then eases between updates. */
export function CountUp({ value, decimals = 0, className }: { value: number; decimals?: number; className?: string }) {
  const el = useRef<HTMLSpanElement>(null);
  const shown = useRef({ v: 0 });
  const armed = useRef(false);
  const fmt = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const run = () => {
      armed.current = true;
      gsap.to(shown.current, {
        v: value,
        duration: prefersReducedMotion() ? 0 : 1.4,
        ease: "power3.out",
        overwrite: true,
        onUpdate: () => {
          node.textContent = fmt(shown.current.v);
        },
      });
    };
    if (armed.current) return run();
    node.textContent = fmt(0);
    if (node.getBoundingClientRect().top < window.innerHeight * 0.92) return run();
    const st = ScrollTrigger.create({
      trigger: node,
      start: "top 92%",
      onEnter: (self) => (self.kill(), run()),
      onLeave: (self) => (self.kill(), run()),
    });
    return () => st.kill();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return <span ref={el} className={cn("num", className)} />;
}

export function Tile({
  className,
  children,
  as: Tag = "section",
  "aria-label": label,
}: {
  className?: string;
  children: React.ReactNode;
  as?: "section" | "div" | "article";
  "aria-label"?: string;
}) {
  return (
    <Tag data-bento data-tilt aria-label={label} className={cn("glass min-w-0 [transform-style:preserve-3d]", className)}>
      {children}
    </Tag>
  );
}

/**
 * Bento grid with two behaviours:
 *  - reveal: tiles unmask from the bottom with a slight 3D fall-back, staggered by row,
 *  - glass: a highlight follows the pointer across each tile, which tilts a few degrees,
 */
export function BentoGrid({ className, children }: { className?: string; children: React.ReactNode }) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const el = root.current;
      if (!el || prefersReducedMotion()) return;
      const tiles = gsap.utils.toArray<HTMLElement>("[data-bento]", el);
      const revealed = new WeakSet<HTMLElement>();
      const reveal = (batch: Element[]) => {
        const fresh = (batch as HTMLElement[]).filter((t) => !revealed.has(t));
        fresh.forEach((t) => revealed.add(t));
        if (!fresh.length) return;
        gsap.to(fresh, {
          autoAlpha: 1,
          y: 0,
          rotateX: 0,
          clipPath: "inset(0% 0% 0% 0% round 10px)",
          duration: 1,
          ease: "power3.out",
          stagger: 0.09,
          clearProps: "clipPath,transform",
        });
      };
      gsap.set(tiles, { autoAlpha: 0, y: 48, rotateX: -10, clipPath: "inset(30% 0% 0% 0% round 10px)", transformPerspective: 1000 });
      // Tiles already on screen (or scrolled past) when the view opens reveal straight away.
      const now = tiles.filter((t) => t.getBoundingClientRect().top < window.innerHeight * 0.88);
      reveal(now);
      ScrollTrigger.batch(
        tiles.filter((t) => !now.includes(t)),
        { start: "top 88%", onEnter: reveal, onEnterBack: reveal, onLeave: reveal },
      );
    },
    { scope: root },
  );

  // Glass sheen + tilt.
  useEffect(() => {
    const el = root.current;
    if (!el || prefersReducedMotion() || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    let active: HTMLElement | null = null;
    const move = (e: PointerEvent) => {
      const tile = (e.target as HTMLElement).closest<HTMLElement>("[data-tilt]");
      if (active && active !== tile) gsap.to(active, { rotateX: 0, rotateY: 0, duration: 0.6, ease: "power3.out" });
      active = tile;
      if (!tile) return;
      const b = tile.getBoundingClientRect();
      const px = (e.clientX - b.left) / b.width;
      const py = (e.clientY - b.top) / b.height;
      tile.style.setProperty("--mx", `${px * 100}%`);
      tile.style.setProperty("--my", `${py * 100}%`);
      // Big tiles tilt less.
      const k = Math.min(1, 320 / Math.max(b.width, b.height));
      gsap.to(tile, { rotateY: (px - 0.5) * 6 * k, rotateX: -(py - 0.5) * 6 * k, transformPerspective: 900, duration: 0.5, ease: "power3.out" });
    };
    const leave = () => {
      if (active) gsap.to(active, { rotateX: 0, rotateY: 0, duration: 0.6, ease: "power3.out" });
      active = null;
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
    };
  }, []);

  return (
    <div ref={root} className={cn("relative isolate", className)}>
      {children}
    </div>
  );
}
