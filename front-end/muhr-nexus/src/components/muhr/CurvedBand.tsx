import { useRef } from "react";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/motion";

const PHRASE = "Sealed input  ✦  Committed result  ✦  Checked invoice  ✦  Key on payment  ✦  ";

/**
 * A line of type set on a gentle SVG curve. Scrolling slides it along the curve, and the
 * curve itself flattens as it reaches the middle of the screen, like a ribbon pulled taut.
 */
export function CurvedBand() {
  const root = useRef<HTMLDivElement>(null);
  const tp = useRef<SVGTextPathElement>(null);
  const path = useRef<SVGPathElement>(null);

  const curve = (bend: number) => `M -40 ${120 - bend} C 360 ${120 + bend}, 1080 ${120 - bend * 1.4}, 1480 ${120 + bend * 0.6}`;

  useGSAP(
    () => {
      if (!root.current || !tp.current || !path.current || prefersReducedMotion()) return;
      const state = { off: 0, bend: 70 };
      const apply = () => {
        tp.current!.setAttribute("startOffset", `${state.off}%`);
        path.current!.setAttribute("d", curve(state.bend));
      };
      gsap.fromTo(
        state,
        { off: 0, bend: 70 },
        {
          off: -50,
          bend: 10,
          ease: "none",
          onUpdate: apply,
          scrollTrigger: { trigger: root.current, start: "top bottom", end: "bottom top", scrub: 0.6 },
        },
      );
    },
    { scope: root },
  );

  return (
    <div ref={root} className="relative -mx-4 overflow-hidden py-6 sm:-mx-6" aria-label="Sealed input, committed result, checked invoice, key on payment">
      <svg viewBox="0 0 1440 240" className="block w-full" aria-hidden>
        <path ref={path} id="muhr-band" d={curve(70)} fill="none" />
        <text className="type-wide" fontSize="56" fontWeight={800} fill="hsl(var(--ink))" letterSpacing="-1">
          <textPath ref={tp} href="#muhr-band" startOffset="0%">
            {PHRASE.repeat(4)}
          </textPath>
        </text>
      </svg>
    </div>
  );
}
