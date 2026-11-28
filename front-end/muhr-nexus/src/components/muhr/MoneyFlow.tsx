import { useId, useRef } from "react";
import { cn } from "@/lib/utils";
import { sats } from "@/lib/format";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/motion";
import { CountUp } from "./Bento";

const COBALT = "#2F4F8A";
const BRASS = "#B08A3E";
const INK = "#172034";
const GREEN = "#178562"; // validated with cobalt, brass and seal (dataviz validator, light)
const SEAL = "#9E2A1F";

const H = 380;
const GAP = 18;
const MIN = 76; // smallest node, so its label fits
const NW = 180; // node width in viewBox units (of 1000)
const MX = 410;
const RX = 1000 - NW;

/** Split the column height between two values, keeping both nodes legible. */
function split(a: number, b: number): [number, number] {
  const avail = H - GAP;
  const t = a + b;
  const ha = t ? Math.min(avail - MIN, Math.max(MIN, (avail * a) / t)) : avail / 2;
  return [ha, avail - ha];
}

function ribbon(xa: number, a0: number, a1: number, xb: number, b0: number, b1: number) {
  const m = (xa + xb) / 2;
  return `M ${xa} ${a0} C ${m} ${a0}, ${m} ${b0}, ${xb} ${b0} L ${xb} ${b1} C ${m} ${b1}, ${m} ${a1}, ${xa} ${a1} Z`;
}

type Node = { key: string; label: string; note: string; value: number; color: string; x: number; y: number; h: number; side: "l" | "m" | "r" };

/**
 * Where the sats went, as one flow: real and demo payments make up the gross, and the
 * gross divides into what sellers kept and the platform fee. Ribbons draw left to right
 * when the diagram scrolls into view.
 */
export function MoneyFlow({ real, demo, gross, net, fee }: { real: number; demo: number; gross: number; net: number; fee: number }) {
  const root = useRef<HTMLDivElement>(null);
  const id = useId().replace(/:/g, "");
  const [hR, hD] = split(real, demo);
  const [hN, hF] = split(net, fee);
  // Ribbons carry the true share (a zero value draws no ribbon). Only the blocks get a
  // minimum size, and each ribbon sits centred on its block.
  const inT = real + demo;
  const outT = net + fee;
  const tR = inT ? (H * real) / inT : 0;
  const tN = outT ? (H * net) / outT : 0;
  const mid = (y: number, h: number, t: number) => y + (h - Math.min(h, t)) / 2;

  const nodes: Node[] = [
    { key: "real", label: "Real Lightning", note: "Paid over a real channel", value: real, color: COBALT, x: 0, y: 0, h: hR, side: "l" },
    { key: "demo", label: "Demo invoices", note: "No sats moved", value: demo, color: BRASS, x: 0, y: hR + GAP, h: hD, side: "l" },
    { key: "gross", label: "Gross paid", note: "Every verified payment to a seller", value: gross, color: INK, x: MX, y: 0, h: H, side: "m" },
    { key: "net", label: "Kept by sellers", note: "Gross minus the fee", value: net, color: GREEN, x: RX, y: 0, h: hN, side: "r" },
    { key: "fee", label: "Platform fee", note: "2%, booked, not collected", value: fee, color: SEAL, x: RX, y: hN + GAP, h: hF, side: "r" },
  ];

  const tD = inT ? H - tR : 0;
  const tF = outT ? H - tN : 0;
  const rY = mid(0, hR, tR);
  const dY = mid(hR + GAP, hD, tD);
  const nY = mid(0, hN, tN);
  const fY = mid(hN + GAP, hF, tF);
  const ribbons = [
    { key: "real", t: tR, d: ribbon(NW, rY, rY + Math.min(hR, tR), MX, 0, tR), from: COBALT, to: INK, stage: "in" },
    { key: "demo", t: tD, d: ribbon(NW, dY, dY + Math.min(hD, tD), MX, tR, H), from: BRASS, to: INK, stage: "in" },
    { key: "net", t: tN, d: ribbon(MX + NW, 0, tN, RX, nY, nY + Math.min(hN, tN)), from: INK, to: GREEN, stage: "out" },
    { key: "fee", t: tF, d: ribbon(MX + NW, tN, H, RX, fY, fY + Math.min(hF, tF)), from: INK, to: SEAL, stage: "out" },
  ].filter((r) => r.t > 0.5);

  useGSAP(
    () => {
      const el = root.current;
      if (!el || prefersReducedMotion()) return;
      const q = gsap.utils.selector(el);
      const tl = gsap.timeline({ paused: true, defaults: { ease: "power3.out" } });
      tl.fromTo(q("[data-node='l']"), { x: -24, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: 0.6, stagger: 0.08 })
        .fromTo(q(`#clip-in-${id} rect`), { attr: { width: 0 } }, { attr: { width: MX - NW }, duration: 0.9, ease: "power2.inOut" }, 0.25)
        .fromTo(q("[data-node='m']"), { scaleY: 0.6, autoAlpha: 0 }, { scaleY: 1, autoAlpha: 1, duration: 0.6, transformOrigin: "50% 50%" }, 0.85)
        .fromTo(q(`#clip-out-${id} rect`), { attr: { width: 0 } }, { attr: { width: RX - MX - NW }, duration: 0.9, ease: "power2.inOut" }, 1.15)
        .fromTo(q("[data-node='r']"), { x: 24, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: 0.6, stagger: 0.08 }, 1.75);
      // Play once when it arrives; if it's already on screen, play now.
      if (el.getBoundingClientRect().top < window.innerHeight * 0.85) tl.play();
      else
        gsap.timeline({
          scrollTrigger: { trigger: el, start: "top 85%", once: true, onEnter: () => void tl.play() },
        });
    },
    { scope: root, dependencies: [id] },
  );

  return (
    <div ref={root}>
      {/* Wide screens: the flow */}
      <div className="relative hidden md:block" style={{ height: H }}>
        <svg viewBox={`0 0 1000 ${H}`} preserveAspectRatio="none" className="absolute inset-0 size-full" aria-hidden>
          <defs>
            {ribbons.map((r) => (
              <linearGradient key={r.key} id={`g-${r.key}-${id}`} x1="0" x2="1" y1="0" y2="0">
                <stop offset="0" stopColor={r.from} stopOpacity="0.3" />
                <stop offset="1" stopColor={r.to} stopOpacity="0.3" />
              </linearGradient>
            ))}
            <clipPath id={`clip-in-${id}`}>
              <rect x={NW} y="0" width={MX - NW} height={H} />
            </clipPath>
            <clipPath id={`clip-out-${id}`}>
              <rect x={MX + NW} y="0" width={RX - MX - NW} height={H} />
            </clipPath>
          </defs>
          {ribbons.map((r) => (
            <path key={r.key} d={r.d} fill={`url(#g-${r.key}-${id})`} clipPath={`url(#clip-${r.stage}-${id})`} />
          ))}
        </svg>
        {nodes.map((n) => (
          <div
            key={n.key}
            data-node={n.side}
            className={cn(
              "absolute flex flex-col justify-between overflow-hidden rounded-[10px] px-4 py-3",
              n.side === "m" ? "clay bg-ink text-sheet [--clay-shade:var(--ink)]" : "glass",
            )}
            style={{ left: `${(n.x / 1000) * 100}%`, width: `${(NW / 1000) * 100}%`, top: n.y, height: n.h }}
          >
            {n.side !== "m" ? (
              <span
                className={cn("absolute inset-y-2 w-[3px] rounded-full", n.side === "l" ? "right-1.5" : "left-1.5")}
                style={{ background: n.color }}
                aria-hidden
              />
            ) : null}
            <div className={cn("text-xs", n.side === "m" ? "text-sheet/70" : "text-graphite")}>{n.label}</div>
            <div>
              <div className={cn("font-semibold leading-none tracking-tight", n.side === "m" ? "text-[2.2rem]" : "text-[1.35rem]")}>
                <CountUp value={n.value} />
                <span className={cn("ml-1 text-xs font-normal tracking-normal", n.side === "m" ? "text-sheet/70" : "text-graphite")}>sats</span>
              </div>
              {n.h >= 96 || n.side === "m" ? (
                <div className={cn("mt-1.5 text-2xs", n.side === "m" ? "text-sheet/60" : "text-graphite")}>{n.note}</div>
              ) : null}
            </div>
          </div>
        ))}
      </div>

      {/* Narrow screens: the same figures as a list */}
      <dl className="space-y-4 md:hidden">
        <div className="clay rounded-[10px] bg-ink px-4 py-4 text-sheet [--clay-shade:var(--ink)]">
          <dt className="text-xs text-sheet/70">Gross paid</dt>
          <dd className="mt-1 text-[2rem] font-semibold leading-none">
            <CountUp value={gross} /> <span className="text-xs font-normal text-sheet/70">sats</span>
          </dd>
        </div>
        {[
          ["Came from", nodes.filter((n) => n.side === "l")],
          ["Went to", nodes.filter((n) => n.side === "r")],
        ].map(([title, group]) => (
          <div key={title as string}>
            <dt className="text-xs font-semibold text-ink">{title as string}</dt>
            {(group as Node[]).map((n) => {
              const tot = (group as Node[]).reduce((a, x) => a + x.value, 0);
              return (
                <dd key={n.key} className="mt-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-graphite">{n.label}</span>
                    <span className="num font-medium">{sats(n.value)} sats</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-rule/70">
                    <div className="muhr-grow h-full rounded-full" style={{ width: `${tot ? (n.value / tot) * 100 : 0}%`, background: n.color }} />
                  </div>
                </dd>
              );
            })}
          </div>
        ))}
      </dl>
    </div>
  );
}
