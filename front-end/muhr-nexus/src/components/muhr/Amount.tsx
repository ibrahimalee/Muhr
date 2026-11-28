import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRates } from "@/hooks/useRates";
import { sats as fmtSats } from "@/lib/format";
import { formatPkr } from "@/lib/pkr";
import { cn } from "@/lib/utils";

function updatedAt(iso: string | null): string {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "unknown";
}

/** The rupee line on its own, for places that already draw the sat number themselves. */
export function PkrNote({ sats, className }: { sats: number | null | undefined; className?: string }) {
  const { rates, stale, fetchedAt } = useRates();
  if (sats == null || !rates) return null;
  const text = `≈ ${formatPkr(sats, rates.sats_pkr)}`;
  if (!stale) return <span className={cn("num whitespace-nowrap text-graphite", className)}>{text}</span>;
  const note = `Approximate rate, last updated ${updatedAt(fetchedAt)}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          title={note}
          aria-label={`${text}. ${note}`}
          className={cn("num cursor-help whitespace-nowrap text-graphite underline decoration-dotted underline-offset-2", className)}
        >
          {text}
        </span>
      </TooltipTrigger>
      <TooltipContent>{note}</TooltipContent>
    </Tooltip>
  );
}

/**
 * A sat amount with its approximate rupee value underneath.
 * `inline` puts them on one line (for sentences and tight rows).
 */
export function Amount({
  sats,
  unit = true,
  inline = false,
  align = "left",
  className,
  pkrClassName,
}: {
  sats: number | null | undefined;
  unit?: boolean;
  inline?: boolean;
  align?: "left" | "right";
  className?: string;
  pkrClassName?: string;
}) {
  if (sats == null) return <span className="text-graphite">–</span>;
  return (
    <span
      className={cn(
        inline ? "inline-flex items-baseline gap-1.5" : "inline-flex flex-col leading-tight",
        !inline && (align === "right" ? "items-end" : "items-start"),
        className,
      )}
    >
      <span className="num">
        {fmtSats(sats)}
        {unit ? <span className="ml-1 text-[0.8em] font-normal text-graphite">sats</span> : null}
      </span>
      <PkrNote sats={sats} className={cn(inline ? "text-[0.85em]" : "text-[0.72em]", pkrClassName)} />
    </span>
  );
}
