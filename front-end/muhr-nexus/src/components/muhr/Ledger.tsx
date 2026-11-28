import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { clockTime, eventLabel, eventTone, sats, shortHash } from "@/lib/format";
import type { FeedEvent } from "@/types/api";
import { EmptyNote, SectionHead } from "./primitives";

const feedStateText = {
  open: "Live",
  connecting: "Connecting",
  error: "Reconnecting",
} as const;

export function Ledger({ events, status, limit = 60, bare }: { events: FeedEvent[]; status: "connecting" | "open" | "error"; limit?: number; bare?: boolean }) {
  const rows = useMemo(() => events.slice(-limit).reverse(), [events, limit]);

  return (
    <section className={cn("flex min-h-0 flex-col", !bare && "sheet")}>
      <div className="border-b border-rule/80 px-5 py-4">
        <SectionHead title="Registry ledger">
          <span className="inline-flex items-center gap-1.5">
            <span className={cn("size-1.5 rounded-full", status === "open" ? "bg-settled" : "bg-pending")} aria-hidden />
            {feedStateText[status]}
          </span>
        </SectionHead>
      </div>
      {rows.length === 0 ? (
        <div className="px-5">
          <EmptyNote>Every step a job takes is written here as it happens: quotes, sealed input, invoices, payments and settlements.</EmptyNote>
        </div>
      ) : (
        <div className="max-h-[420px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-sheet/85 text-left text-2xs text-graphite backdrop-blur">
              <tr className="border-b border-rule">
                <th className="py-2 pl-5 pr-3 font-medium">Time</th>
                <th className="px-3 py-2 font-medium">Entry</th>
                <th className="hidden px-3 py-2 font-medium sm:table-cell">Reference</th>
                <th className="py-2 pl-3 pr-5 text-right font-medium">Sats</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e, i) => {
                const tone = eventTone(e.type);
                const ref = e.job_id ?? e.task_id ?? e.seller_id ?? null;
                return (
                  <tr
                    key={`${e.timestamp}:${e.type}:${ref}:${events.length - i}`}
                    className={cn("muhr-row border-b border-rule/70 last:border-0", i === 0 && "muhr-new-row")}
                  >
                    <td className="num whitespace-nowrap py-2.5 pl-5 pr-3 align-top text-xs text-graphite">{clockTime(e.timestamp)}</td>
                    <td className="px-3 py-2.5 align-top">
                      <span className={cn("font-medium", tone === "bad" && "text-seal", tone === "money" && "text-settled")}>{eventLabel(e.type)}</span>
                      {e.detail ? <span className="block max-w-[52ch] text-xs text-graphite">{e.detail}</span> : null}
                    </td>
                    <td className="hidden px-3 py-2.5 align-top sm:table-cell">
                      <span className="hash text-xs text-ink-soft">{ref ? shortHash(ref, 10, 4) : "–"}</span>
                    </td>
                    <td className="num whitespace-nowrap py-2.5 pl-3 pr-5 text-right align-top font-medium">
                      {e.amount_sats == null ? <span className="text-graphite">–</span> : sats(e.amount_sats)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
