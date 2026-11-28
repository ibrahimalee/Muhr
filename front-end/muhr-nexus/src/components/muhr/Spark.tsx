import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion, ScrollTrigger } from "@/lib/motion";

/**
 * A small area sparkline whose line draws itself when it scrolls into view.
 * Single series, so no legend; the tile's label names it.
 */
export function Spark({ values, color = "#2F4F8A", label }: { values: number[]; color?: string; label: string }) {
  const line = useRef<SVGPathElement>(null);
  const area = useRef<SVGPathElement>(null);
  const W = 240;
  const H = 56;
  const pts = values.length > 1 ? values : [0, ...(values.length ? values : [0])];
  const max = Math.max(1, ...pts);
  const xy = pts.map((v, i) => [(i / (pts.length - 1)) * W, H - 4 - (v / max) * (H - 10)] as const);
  // Smooth with a simple cardinal-ish curve.
  const d = xy.reduce((acc, [x, y], i) => {
    if (i === 0) return `M ${x} ${y}`;
    const [px, py] = xy[i - 1]!;
    const cx = (px + x) / 2;
    return `${acc} C ${cx} ${py}, ${cx} ${y}, ${x} ${y}`;
  }, "");
  const fill = `${d} L ${W} ${H} L 0 ${H} Z`;
  const id = `spark-${label.replace(/\W/g, "")}`;

  useEffect(() => {
    const l = line.current;
    if (!l) return;
    const len = l.getTotalLength();
    if (prefersReducedMotion()) return;
    gsap.set(l, { strokeDasharray: len, strokeDashoffset: len });
    gsap.set(area.current, { autoAlpha: 0 });
    const run = () => {
      gsap.to(l, { strokeDashoffset: 0, duration: 1.6, ease: "power2.inOut" });
      gsap.to(area.current, { autoAlpha: 1, duration: 1.2, delay: 0.6 });
    };
    if (l.getBoundingClientRect().top < window.innerHeight * 0.95) return run();
    const st = ScrollTrigger.create({ trigger: l, start: "top 95%", onEnter: (s) => (s.kill(), run()), onLeave: (s) => (s.kill(), run()) });
    return () => st.kill();
  }, [d]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-14 w-full" role="img" aria-label={label}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.22" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path ref={area} d={fill} fill={`url(#${id})`} />
      <path ref={line} d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
