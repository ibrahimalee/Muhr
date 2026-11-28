import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { capabilityLabel, relativeTime } from "@/lib/format";
import { PITCH_PRESETS, PITCH_STAGES, pitchTrack, type PitchPreset } from "@/lib/pitch";
import { receiptPath } from "@/lib/receipt";
import { cn } from "@/lib/utils";
import type { DemoRunResponse, FeedEvent, JobSummary } from "@/types/api";
import { Amount } from "./Amount";
import { SealMark, StatusMark } from "./primitives";
import { useRates } from "@/hooks/useRates";

/**
 * A single-screen layout for a live demo on a projector: one big button, one big tracker, one
 * short ledger. Base text is 20px or larger, contrast is high, and nothing depends on hover.
 */
export function PitchView({
  events,
  feedStatus,
  jobs,
  demoMode,
  busy,
  result,
  error,
  onRun,
  onExit,
}: {
  events: FeedEvent[];
  feedStatus: "connecting" | "open" | "error";
  jobs: JobSummary[] | undefined;
  demoMode: boolean | undefined;
  busy: boolean;
  result: DemoRunResponse | null;
  error: string | null;
  onRun: (preset: PitchPreset) => void;
  onExit: () => void;
}) {
  const [picking, setPicking] = useState(false);
  // Events seen before the presenter pressed a button belong to earlier jobs.
  const [baseline, setBaseline] = useState<FeedEvent | null>(null);
  const fromIndex = useMemo(() => {
    if (!baseline) return events.length;
    const i = events.lastIndexOf(baseline);
    return i < 0 ? 0 : i + 1;
  }, [events, baseline]);
  const track = useMemo(() => pitchTrack(events, fromIndex), [events, fromIndex]);
  const { rates, stale } = useRates();

  const start = (p: PitchPreset) => {
    setBaseline(events[events.length - 1] ?? null);
    setPicking(false);
    onRun(p);
  };

  const recent = (jobs ?? []).slice(0, 5);
  const live = feedStatus === "open";
  const reconnecting = !live;
  const activeStage = track.broken ? -1 : Math.min(track.reached, PITCH_STAGES.length - 1);

  return (
    <div className="min-h-screen bg-paper text-ink [font-size:1.25rem] [line-height:1.5]">
      <div className="mx-auto flex min-h-screen max-w-[1500px] flex-col gap-6 px-5 py-5 sm:px-8 sm:py-7">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <SealMark className="size-10" />
            <span className="type-wide text-[1.75rem] font-extrabold">Muhr</span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={cn(
                "inline-flex items-center gap-2 rounded-full border-2 px-4 py-1.5 font-bold",
                demoMode === false ? "border-settled bg-settled-tint text-settled" : "border-pending bg-pending-tint text-ink",
              )}
              role="status"
            >
              {demoMode === false ? "REAL MODE: real Lightning payments" : demoMode === true ? "DEMO MODE: no real money moves" : "Mode unknown"}
            </span>
            <span
              role="status"
              className={cn(
                "inline-flex items-center gap-2 rounded-full px-4 py-1.5 font-semibold",
                reconnecting ? "bg-pending-tint text-ink" : "bg-secondary text-ink-soft",
              )}
            >
              <span className={cn("size-3 rounded-full", reconnecting ? "bg-pending motion-safe:animate-pulse" : "bg-settled")} aria-hidden />
              {reconnecting ? "Reconnecting…" : "Live"}
            </span>
            <button type="button" onClick={onExit} className="rounded-full border-2 border-ink px-4 py-1.5 font-semibold hover:bg-ink hover:text-sheet">
              Exit pitch mode (P)
            </button>
          </div>
        </header>

        <div className="grid flex-1 gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          {/* (a) Hire */}
          <section aria-label="Hire a seller" className="glass flex flex-col gap-5 p-6 sm:p-8">
            <Button
              variant="seal"
              className="muhr-arrow h-auto min-h-20 w-full whitespace-normal py-5 text-[1.75rem] font-bold sm:text-[2rem]"
              onClick={() => setPicking((v) => !v)}
              disabled={busy}
              aria-expanded={picking}
            >
              {busy ? <Loader2 className="size-8 motion-safe:animate-spin" aria-hidden /> : null}
              {busy ? "Job running…" : "Hire a seller"}
              {busy ? null : <ArrowRight className="size-8" aria-hidden />}
            </Button>

            {picking && !busy ? (
              <ul className="grid gap-3">
                {PITCH_PRESETS.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => start(p)}
                      className="clay block w-full rounded-[10px] bg-sheet px-5 py-4 text-left [--clay-shade:var(--rule-strong)] hover:bg-secondary"
                    >
                      <span className="block text-[1.4rem] font-bold leading-tight">{p.label}</span>
                      <span className="block text-ink-soft">
                        {p.hint}, up to <Amount sats={p.budget} inline unit /> budget
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-ink-soft">
                {busy
                  ? "The stages on the right light up as the registry records each one."
                  : "Pick a task. A seller is hired, the input is sealed to it, and the result unlocks when the invoice is paid."}
              </p>
            )}

            {error ? (
              <div role="alert" className="flex items-start gap-3 rounded-[8px] border-2 border-seal bg-seal-tint px-4 py-3 font-medium">
                <X className="mt-1 size-6 shrink-0 text-seal" aria-hidden />
                <span className="min-w-0 break-words">{error}</span>
              </div>
            ) : null}

            {result && !busy ? (
              <div className="rounded-[8px] border-2 border-settled bg-settled-tint px-4 py-3" role="status">
                <div className="flex flex-wrap items-center justify-between gap-2 font-bold text-settled">
                  <span className="inline-flex items-center gap-2">
                    <Check className="size-6" aria-hidden /> Result decrypted after payment
                  </span>
                  <Link to={receiptPath(result.job_id)} className="underline decoration-2 underline-offset-4">
                    View receipt
                  </Link>
                </div>
                <blockquote dir="auto" className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-urdu text-[1.25rem] leading-relaxed">
                  {result.result_preview}
                </blockquote>
              </div>
            ) : null}
          </section>

          {/* (b) Tracker */}
          <section aria-label="Live job tracker" className="glass flex flex-col p-6 sm:p-8">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="type-wide text-[1.75rem] font-extrabold">Live job</h2>
              <span className="text-ink-soft" aria-live="polite">
                {track.broken
                  ? `Stopped: ${track.broken.kind}${track.broken.detail ? `, ${track.broken.detail}` : ""}`
                  : track.done
                    ? "Settled"
                    : track.reached
                      ? `Stage ${track.reached} of ${PITCH_STAGES.length}`
                      : "Waiting for a job"}
              </span>
            </div>
            <ol className="mt-5 grid gap-3 sm:grid-cols-2">
              {PITCH_STAGES.map((s, i) => {
                const at = track.times[i];
                const isLit = Boolean(at);
                const isNext = !track.broken && !isLit && i === activeStage && busy;
                return (
                  <li
                    key={s.id}
                    data-lit={isLit}
                    className={cn(
                      "flex items-center gap-4 rounded-[10px] border-2 px-4 py-3 motion-safe:transition-colors motion-safe:duration-500",
                      isLit ? "border-settled bg-settled-tint" : "border-rule-strong bg-sheet/60",
                      isNext && "border-ink",
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-10 shrink-0 place-items-center rounded-full border-2 font-bold motion-safe:transition-colors motion-safe:duration-500",
                        isLit ? "border-settled bg-settled text-sheet" : "border-rule-strong text-ink-soft",
                      )}
                      aria-hidden
                    >
                      {isLit ? <Check className="size-6" /> : isNext ? <Loader2 className="size-5 motion-safe:animate-spin" /> : i + 1}
                    </span>
                    <span className="min-w-0">
                      <span className={cn("block text-[1.25rem] font-bold leading-tight", !isLit && "text-ink-soft")}>{s.name}</span>
                      <span className="sr-only">{isLit ? "done" : "not yet"}</span>
                    </span>
                  </li>
                );
              })}
            </ol>
          </section>
        </div>

        {/* (c) Ledger */}
        <section aria-label="Recent jobs" className="glass p-6 sm:p-8">
          <h2 className="type-wide text-[1.75rem] font-extrabold">Last 5 jobs</h2>
          {recent.length ? (
            <ul className="mt-3 divide-y-2 divide-rule">
              {recent.map((j) => (
                <li key={j.job_id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-3">
                  <span className="min-w-0">
                    <span className="block font-bold">{capabilityLabel(j.capability)}</span>
                    <span className="text-ink-soft">{relativeTime(j.created_at)}</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-x-5 gap-y-1">
                    <Amount sats={j.accepted_price_sats ?? j.budget_sats} className="font-bold" pkrClassName="text-[1.1rem] text-ink-soft" />
                    <StatusMark status={j.status} className="px-3 py-1 text-[1.1rem]" />
                    {j.status === "settled" ? (
                      <Link to={receiptPath(j.job_id)} className="font-semibold underline decoration-seal decoration-2 underline-offset-4">
                        View receipt
                      </Link>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-ink-soft">No jobs yet. Hire a seller to start one.</p>
          )}
          {rates && stale ? <p className="mt-4 text-ink-soft">Rupee amounts use an approximate, possibly out-of-date rate.</p> : null}
        </section>
      </div>
    </div>
  );
}
