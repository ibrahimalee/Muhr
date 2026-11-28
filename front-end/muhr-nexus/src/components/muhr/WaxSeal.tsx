import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * A clay wax seal: an irregular rim, an embossed M, and the protocol's promise set on a
 * circular text path. `legendRef` lets a parent rotate the legend (it turns with scroll).
 */
export function WaxSeal({
  className,
  legend = "Sealed input  ✦  Committed result  ✦  Key on payment  ✦  ",
  legendRef,
  tone = "seal",
}: {
  className?: string;
  legend?: string;
  legendRef?: React.Ref<SVGGElement>;
  tone?: "seal" | "ghost";
}) {
  const id = useId().replace(/:/g, "");
  const ghost = tone === "ghost";
  // A wobbly rim, like poured wax.
  const rim = Array.from({ length: 28 }, (_, i) => {
    const a = (i / 28) * Math.PI * 2;
    const r = 96 + (i % 2 ? 3.2 : -1.6) + Math.sin(i * 1.7) * 2.2;
    return `${(100 + Math.cos(a) * r).toFixed(1)},${(100 + Math.sin(a) * r).toFixed(1)}`;
  }).join(" ");

  return (
    <svg viewBox="0 0 200 200" className={cn("overflow-visible", className)} aria-hidden>
      <defs>
        <radialGradient id={`body-${id}`} cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="hsl(6 62% 52%)" />
          <stop offset="55%" stopColor="hsl(var(--seal))" />
          <stop offset="100%" stopColor="hsl(var(--seal-deep))" />
        </radialGradient>
        <radialGradient id={`dish-${id}`} cx="60%" cy="66%" r="70%">
          <stop offset="0%" stopColor="hsl(6 60% 46%)" />
          <stop offset="100%" stopColor="hsl(5 70% 30%)" />
        </radialGradient>
        <filter id={`soft-${id}`} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="0.6" />
        </filter>
        <path id={`ring-${id}`} d="M100,100 m-70,0 a70,70 0 1,1 140,0 a70,70 0 1,1 -140,0" />
      </defs>

      {ghost ? (
        <>
          <circle cx="100" cy="100" r="96" fill="none" stroke="hsl(var(--ink) / 0.10)" strokeWidth="1" />
          <circle cx="100" cy="100" r="56" fill="none" stroke="hsl(var(--ink) / 0.10)" strokeWidth="1" />
        </>
      ) : (
        <>
          <polygon points={rim} fill={`url(#body-${id})`} filter={`url(#soft-${id})`} />
          <circle cx="100" cy="100" r="58" fill={`url(#dish-${id})`} />
          <circle cx="100" cy="100" r="58" fill="none" stroke="hsl(0 0% 100% / 0.18)" strokeWidth="1.2" />
          {/* Embossed M: a highlight offset up-left, a shadow down-right */}
          <g strokeLinecap="square" strokeLinejoin="miter" fill="none" strokeWidth="11">
            <path d="M78 130V74l22 32 22-32v56" stroke="hsl(5 72% 22% / 0.7)" transform="translate(1.8 2.2)" />
            <path d="M78 130V74l22 32 22-32v56" stroke="hsl(6 55% 58%)" />
            <path d="M78 130V74l22 32 22-32v56" stroke="hsl(0 0% 100% / 0.22)" strokeWidth="3" transform="translate(-2 -2)" />
          </g>
        </>
      )}

      <g ref={legendRef} style={{ transformOrigin: "100px 100px" }}>
        <text
          fontSize="11.5"
          fontWeight={700}
          letterSpacing="2.4"
          fill={ghost ? "hsl(var(--ink) / 0.28)" : "hsl(0 0% 100% / 0.78)"}
          style={{ fontVariationSettings: "'wdth' 112", textTransform: "uppercase" }}
        >
          <textPath href={`#ring-${id}`} startOffset="0" textLength={2 * Math.PI * 70 - 6} lengthAdjust="spacing">
            {legend}
          </textPath>
        </text>
      </g>
    </svg>
  );
}
