import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { STAGES, capabilityLabel, clockTime, sats, shortHash, type JobTrack } from "@/lib/format";
import { ModeMark } from "./primitives";

const N = STAGES.length;
const LAST = N - 1;
// The span of the line where data is sealed: input sealed (2) to paid (5).
const SEAL_FROM = 2;
const SEAL_TO = 5;

/** Horizontal offset (as CSS calc) of station i along a line drawn between the first and last column centres. */
function at(i: number) {
  return `calc(100% / ${N * 2} + (100% - 100% / ${N}) * ${i / LAST})`;
}
function span(from: number, to: number) {
  return `calc((100% - 100% / ${N}) * ${(to - from) / LAST})`;
}

type StationState = "done" | "current" | "next" | "broken";

function stationState(i: number, track: JobTrack): StationState {
  if (track.broken && i === track.reached + 1) return "broken";
  if (i < track.reached || (i === track.reached && i === LAST)) return "done";
  if (i === track.reached) return track.broken ? "done" : "current";
  return "next";
}

function Dot({ state, keyId }: { state: StationState; keyId: string }) {
  if (state === "broken") {
    return (
      <span className="relative z-10 grid size-[18px] place-items-center rounded-full bg-seal text-sheet">
        <X className="size-3" strokeWidth={3} />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "relative z-10 block size-[18px] rounded-full border-[3px] transition-colors duration-500",
        state === "done" && "border-ink bg-ink shadow-[inset_0_1.5px_0_hsl(0_0%_100%/.3),0_4px_8px_-3px_hsl(var(--ink)/.6)]",
        state === "current" && "border-ink bg-sheet shadow-[0_4px_10px_-3px_hsl(var(--ink)/.5)]",
        state === "next" && "border-rule-strong bg-sheet shadow-[inset_0_-1.5px_0_hsl(var(--rule-strong)/.6)]",
      )}
    >
      {state === "current" ? (
        <span key={keyId} className="muhr-arrive absolute -inset-[7px] rounded-full border-2 border-seal" aria-hidden />
      ) : null}
    </span>
  );
}

function brokenText(track: JobTrack) {
  if (!track.broken) return null;
  const where = STAGES[Math.min(track.reached + 1, LAST)]!.name.toLowerCase();
  const what = track.broken.kind === "timeout" ? "Timed out" : track.broken.kind === "dispute" ? "Disputed" : "Failed";
  return `${what} before “${where}”.${track.broken.detail ? ` ${track.broken.detail}` : ""}`;
}

export function JobLine({ track, onRun, loading }: { track: JobTrack; onRun?: () => void; loading?: boolean }) {
  const box = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e?.isIntersecting && setSeen(true), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  // The ink is drawn in once the line scrolls into view, then follows the job live.
  const progress = seen ? Math.max(0, track.reached) / LAST : 0;
  const coinAt = Math.max(0, track.reached);
  const keyId = `${track.jobId}:${track.reached}`;
  const settled = track.reached === LAST;

  return (
    <section ref={box} aria-labelledby="line-title" className="glass overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-rule px-5 py-4 md:px-7">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="line-title" className="text-lg font-semibold tracking-tight">
            {track.jobId ? capabilityLabel(track.capability) : loading ? "Loading the latest job" : "No job on the line yet"}
          </h2>
          {track.jobId ? <span className="hash text-graphite">{shortHash(track.jobId, 10, 4)}</span> : null}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <ModeMark mode={track.mode} />
          {track.amount != null ? (
            <span className="num font-semibold">
              {sats(track.amount)} <span className="font-normal text-graphite">sats</span>
            </span>
          ) : null}
          <span className={cn("text-xs", settled ? "text-settled" : track.broken ? "text-seal" : "text-graphite")}>
            {settled ? "Settled" : track.broken ? "Stopped" : track.reached >= 0 ? `Stage ${track.reached + 1} of ${N}` : ""}
          </span>
        </div>
      </header>

      {/* Desktop: a transit line, one station per protocol stage. */}
      <div className="hidden px-7 pb-6 pt-8 md:block">
        <div className="relative">
          <div className="absolute top-[7px] h-[4px] rounded-full bg-rule" style={{ left: at(0), width: span(0, LAST) }} aria-hidden />
          <div
            className="absolute top-[7px] h-[4px] rounded-full bg-ink transition-[width] duration-[1400ms] ease-[cubic-bezier(.2,.7,.2,1)]"
            style={{ left: at(0), width: `calc(${span(0, LAST)} * ${progress})` }}
            aria-hidden
          />
          {/* Sealed span */}
          <div
            className="absolute top-[22px] h-[3px] rounded-full bg-seal/80"
            style={{ left: at(SEAL_FROM), width: span(SEAL_FROM, SEAL_TO) }}
            aria-hidden
          />
          {track.jobId ? (
            <span
              className="muhr-coin absolute top-[-26px] z-20 -ml-[11px] transition-[left] duration-[1400ms] ease-[cubic-bezier(.2,.7,.2,1)]"
              style={{ left: seen ? at(coinAt) : at(0) }}
              title={track.amount != null ? `${sats(track.amount)} sats` : undefined}
              aria-hidden
            />
          ) : null}
          <span data-route-end className="absolute top-[9px] size-px" style={{ left: at(0) }} aria-hidden />
          <ol className="relative grid" style={{ gridTemplateColumns: `repeat(${N}, minmax(0, 1fr))` }}>
            {STAGES.map((s, i) => {
              const state = stationState(i, track);
              return (
                <li key={s.id} className="flex flex-col items-center px-1 text-center">
                  <Dot state={state} keyId={keyId} />
                  <div className={cn("mt-6 text-sm font-semibold leading-tight", state === "next" && "text-graphite")}>{s.name}</div>
                  <div className="mt-1 max-w-[17ch] text-2xs text-graphite">{s.note}</div>
                  <div className={cn("num mt-2 text-2xs", track.times[i] ? "text-ink-soft" : "text-transparent")}>
                    {track.times[i] ? clockTime(track.times[i]) : "–"}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      {/* Mobile: the same line, vertical. */}
      <ol className="relative px-5 py-5 md:hidden">
        <span className="absolute bottom-8 left-[28px] top-8 w-[3px] rounded-full bg-rule" aria-hidden />
        {STAGES.map((s, i) => {
          const state = stationState(i, track);
          const sealed = i >= SEAL_FROM && i <= SEAL_TO;
          return (
            <li key={s.id} className="relative flex gap-4 py-2">
              <Dot state={state} keyId={keyId} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className={cn("text-sm font-semibold", state === "next" && "text-graphite")}>
                    {s.name}
                    {sealed ? <span className="ml-2 inline-block size-1.5 -translate-y-0.5 rounded-full bg-seal" aria-label="sealed" /> : null}
                  </span>
                  <span className="num text-2xs text-ink-soft">{track.times[i] ? clockTime(track.times[i]) : ""}</span>
                </div>
                <div className="text-2xs text-graphite">{s.note}</div>
              </div>
            </li>
          );
        })}
      </ol>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-rule bg-paper/50 px-5 py-3 text-xs text-graphite md:px-7">
        <span className="flex items-center gap-2">
          <span className="inline-block h-[3px] w-6 rounded-full bg-seal/80" aria-hidden />
          Sealed: from input to payment, only the seller can read the data and nobody can read the result.
        </span>
        {track.broken ? <span className="text-seal">{brokenText(track)}</span> : null}
        {!track.jobId && !loading && onRun ? (
          <button type="button" onClick={onRun} className="font-semibold text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink">
            Run a job to watch it move
          </button>
        ) : null}
      </footer>
    </section>
  );
}
