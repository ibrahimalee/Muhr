import { useRef } from "react";
import { COMPARISON_ROWS, JOB_PRICE_PKR, MUHR_ROW, keeps, type FeeRow } from "@/config/feeComparison";
import { gsap, prefersReducedMotion, useGSAP } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { Tile } from "./Bento";

function Row({ row, highlight }: { row: FeeRow; highlight?: boolean }) {
  const kept = keeps(row);
  const fee = JOB_PRICE_PKR - kept;
  const keptPct = (kept / JOB_PRICE_PKR) * 100;
  return (
    <li className="py-3.5 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
        <span className={cn("text-sm", highlight ? "font-semibold text-ink" : "text-ink-soft")}>{row.name}</span>
        <span className="num text-sm">
          <span className={cn("font-semibold", highlight && "text-settled")}>Seller keeps Rs {kept.toLocaleString("en-US")}</span>
          <span className="ml-2 text-graphite">fee {row.feePercent}% = Rs {fee.toLocaleString("en-US")}</span>
        </span>
      </div>
      <div
        className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-rule/60"
        role="img"
        aria-label={`${row.name}: seller keeps Rs ${kept} of Rs ${JOB_PRICE_PKR}`}
      >
        <span data-bar className={cn("h-full origin-left", highlight ? "bg-settled" : "bg-graphite/60")} style={{ width: `${keptPct}%` }} />
        <span data-bar-fee className="h-full bg-seal/80" style={{ width: `${100 - keptPct}%` }} />
      </div>
      <p className="mt-1.5 text-2xs text-graphite">{row.note}</p>
    </li>
  );
}

/** What a seller keeps from a Rs 1,000 job. The comparison rows are placeholders (see config). */
export function FeeComparison() {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      const el = root.current;
      if (!el || prefersReducedMotion()) return;
      const bars = el.querySelectorAll("[data-bar]");
      const fees = el.querySelectorAll("[data-bar-fee]");
      gsap.set(bars, { scaleX: 0 });
      gsap.set(fees, { autoAlpha: 0 });
      const tl = gsap.timeline({ paused: true, defaults: { ease: "power3.out" } });
      tl.to(bars, { scaleX: 1, duration: 1, stagger: 0.14 }).to(fees, { autoAlpha: 1, duration: 0.4, stagger: 0.14 }, 0.5);
      if (el.getBoundingClientRect().top < window.innerHeight * 0.9) tl.play();
      else gsap.timeline({ scrollTrigger: { trigger: el, start: "top 88%", once: true, onEnter: () => void tl.play() } });
    },
    { scope: root },
  );

  return (
    <Tile className="p-5 md:p-7" aria-label="What a seller keeps from a Rs 1,000 job">
      <div ref={root}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h3 className="type-wide text-xl font-bold leading-tight">What a seller keeps from a Rs 1,000 job</h3>
          <span className="rounded-full border border-pending/40 bg-pending-tint px-2.5 py-0.5 text-2xs font-medium text-pending">
            Illustrative, check current fees
          </span>
        </div>
        <ul className="mt-6 divide-y divide-rule/70">
          <Row row={MUHR_ROW} highlight />
          {COMPARISON_ROWS.map((r) => (
            <Row key={r.name} row={r} />
          ))}
        </ul>
        <p className="mt-5 max-w-[62ch] text-xs leading-relaxed text-graphite">
          Muhr&rsquo;s 2% is the fee the registry actually charges. The other rows are placeholders for typical services, not quotes from any
          named company.
        </p>
      </div>
    </Tile>
  );
}
