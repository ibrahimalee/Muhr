import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { gsap, prefersReducedMotion } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { STAGES, stageOfJob, capabilityLabel, clockTime, relativeTime, sats, shortHash, statusTone } from "@/lib/format";
import type { JobSummary } from "@/types/api";
import { EmptyNote, HashField, ModeMark, StatusMark } from "./primitives";
import { Segmented } from "./Segmented";
import { WaxSeal } from "./WaxSeal";

type FilterId = "all" | "open" | "settled" | "broken";

function matches(job: JobSummary, f: FilterId) {
  const tone = statusTone(job.status);
  if (f === "all") return true;
  if (f === "open") return tone === "pending";
  if (f === "settled") return tone === "settled";
  return tone === "broken";
}

/** Which recorded time belongs to which stage (the registry keeps four of the seven). */
function stageTime(job: JobSummary, id: string): string | null {
  if (id === "posted") return job.created_at;
  if (id === "quoted") return job.committed_at;
  if (id === "committed") return job.delivered_at;
  if (id === "settled") return job.settled_at;
  return null;
}

const ROW = 34; // px per stage row

/** The job's route as a vertical track. The ink line runs down to the furthest stage reached. */
function StageTrack({ job }: { job: JobSummary }) {
  const root = useRef<HTMLOListElement>(null);
  const reached = stageOfJob(job);
  const broken = job.status === "failed" || job.status === "timeout";

  useLayoutEffect(() => {
    const el = root.current;
    if (!el || prefersReducedMotion()) return;
    const q = gsap.utils.selector(el);
    const tl = gsap.timeline({ delay: 0.15 });
    tl.fromTo(q("[data-track-ink]"), { scaleY: 0 }, { scaleY: 1, duration: 0.25 + 0.12 * Math.max(0, reached), ease: "power2.inOut" }, 0);
    tl.fromTo(
      q("[data-station]"),
      { scale: 0.3, autoAlpha: 0 },
      { scale: 1, autoAlpha: 1, duration: 0.4, ease: "back.out(2.2)", stagger: 0.09 },
      0,
    );
    tl.fromTo(q("[data-stage-label]"), { x: -6, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: 0.4, ease: "power3.out", stagger: 0.06 }, 0.05);
    return () => {
      tl.kill();
    };
  }, [job.job_id, reached]);

  return (
    <ol ref={root} className="relative mt-6" aria-label="Progress">
      <span className="absolute left-[6px] w-[2px] rounded-full bg-rule" style={{ top: ROW / 2, height: ROW * (STAGES.length - 1) }} aria-hidden />
      {reached > 0 ? (
        <span
          data-track-ink
          className="absolute left-[6px] w-[2px] origin-top rounded-full bg-ink"
          style={{ top: ROW / 2, height: ROW * reached }}
          aria-hidden
        />
      ) : null}
      {STAGES.map((s, i) => {
        const done = i <= reached;
        const isBreak = broken && i === reached + 1;
        const t = stageTime(job, s.id);
        return (
          <li key={s.id} className="relative flex items-center gap-3 text-sm" style={{ height: ROW }}>
            <span
              data-station
              className={cn(
                "relative z-10 size-3.5 shrink-0 rounded-full",
                isBreak
                  ? "clay bg-seal [--clay-shade:var(--seal-deep)]"
                  : done
                    ? "clay bg-ink [--clay-shade:var(--ink)]"
                    : "border-2 border-rule-strong bg-sheet",
              )}
              aria-hidden
            />
            <span data-stage-label className={cn("flex-1", !done && !isBreak && "text-graphite", isBreak && "font-medium text-seal")}>
              {s.name}
              {isBreak ? (job.status === "timeout" ? ", timed out" : ", failed") : ""}
              <span className="sr-only">{done ? " (reached)" : isBreak ? "" : " (not reached)"}</span>
            </span>
            {t && done ? <span className="num text-xs text-graphite">{clockTime(t)}</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

/** The selected job as a case file. It turns in like a page when another job is picked. */
function JobDetail({ job, sellerName }: { job: JobSummary; sellerName: string }) {
  const root = useRef<HTMLElement>(null);
  const price = job.accepted_price_sats ?? job.budget_sats;
  const settled = job.status === "settled";
  const latency =
    job.delivered_at && job.committed_at ? (new Date(job.delivered_at).getTime() - new Date(job.committed_at).getTime()) / 1000 : null;

  useLayoutEffect(() => {
    const el = root.current;
    if (!el || prefersReducedMotion()) return;
    const tl = gsap.timeline();
    tl.fromTo(
      el,
      { rotateY: -10, x: -14, autoAlpha: 0, transformPerspective: 1400, transformOrigin: "0% 50%" },
      { rotateY: 0, x: 0, autoAlpha: 1, duration: 0.6, ease: "power3.out", clearProps: "transform" },
    );
    const seal = el.querySelector("[data-file-seal]");
    if (seal) {
      tl.fromTo(
        seal,
        { scale: 1.9, rotate: -38, autoAlpha: 0 },
        { scale: 1, rotate: -12, autoAlpha: 1, duration: 0.45, ease: "power4.in" },
        0.45,
      ).to(seal, { scale: 1.04, duration: 0.08, yoyo: true, repeat: 1, ease: "power1.out" });
    }
    return () => {
      tl.kill();
    };
  }, [job.job_id]);

  return (
    <article ref={root} className="glass relative p-5 md:p-6">
      {settled ? (
        <div data-file-seal className="pointer-events-none absolute -right-3 -top-5 size-[74px] -rotate-12 drop-shadow-[0_8px_10px_hsl(var(--seal-deep)/0.35)]" aria-hidden>
          <WaxSeal className="size-full" legend="Settled  ✦  Key released  ✦  Hash matched  ✦  " />
        </div>
      ) : null}

      <div className={cn("flex flex-wrap items-start justify-between gap-3", settled && "pr-14")}>
        <div className="min-w-0">
          <p className="hash text-2xs text-graphite">{shortHash(job.job_id, 14, 6)}</p>
          <h2 className="type-wide mt-1 text-[1.65rem] font-bold leading-tight">{capabilityLabel(job.capability)}</h2>
          <p className="mt-1 text-sm text-graphite">
            Sold by {sellerName}, posted {relativeTime(job.created_at)}
          </p>
        </div>
        {settled ? null : <StatusMark status={job.status} />}
      </div>

      <dl className="mt-5 grid grid-cols-3 border-y border-rule text-sm">
        {[
          ["Price", `${sats(price)}`, "sats"],
          ["Budget", `${sats(job.budget_sats)}`, "sats"],
          ["Turnaround", latency != null ? latency.toFixed(1) : "–", latency != null ? "s" : ""],
        ].map(([k, v, u], i) => (
          <div key={k} className={cn("py-3.5", i > 0 && "border-l border-rule pl-4")}>
            <dt className="text-xs text-graphite">{k}</dt>
            <dd className="mt-1">
              <span className="num text-xl font-semibold tracking-tight">{v}</span>
              {u ? <span className="ml-1 text-xs text-graphite">{u}</span> : null}
            </dd>
          </div>
        ))}
      </dl>

      <StageTrack job={job} />

      <h3 className="mt-7 text-sm font-semibold">What the seller committed to</h3>
      <p className="mt-1 text-xs leading-relaxed text-graphite">
        Recorded at the registry before payment. If the decrypted result doesn&rsquo;t match, the buyer can dispute it and the seller loses half its
        stake.
      </p>
      <dl className="mt-2 divide-y divide-rule border-y border-rule">
        <HashField label="Result hash" value={job.result_hash} hint="sha256 of the plaintext" decode={0.2} />
        <HashField label="Key commitment" value={job.key_commitment} hint="sha256 of the result key" decode={0.3} />
        <HashField label="Ciphertext hash" value={job.ciphertext_hash} decode={0.4} />
        <HashField label="Pipeline hash" value={job.computation_hash} hint="Model chain, image and price" decode={0.5} />
      </dl>

      <h3 className="mt-7 flex items-center gap-2 text-sm font-semibold">
        Payment <ModeMark mode={job.lightning_mode} />
      </h3>
      <dl className="mt-2 divide-y divide-rule border-y border-rule">
        <HashField label="Invoice hash" value={job.payment_hash} hint="The lock on this job" decode={0.6} />
        <HashField label="Paid hash" value={job.lightning_payment_hash} decode={0.7} />
        <div className="grid gap-1 py-2.5 text-sm sm:grid-cols-[10.5rem_1fr] sm:gap-4">
          <dt className="text-xs text-graphite">Key released by</dt>
          <dd>{job.key_release === "seller_confirmed" ? "Seller, after its wallet saw the payment" : job.key_release === "preimage" ? "The payment preimage" : "–"}</dd>
        </div>
        <div className="grid gap-1 py-2.5 text-sm sm:grid-cols-[10.5rem_1fr] sm:gap-4">
          <dt className="text-xs text-graphite">Payment verified</dt>
          <dd className={job.payment_verified ? "text-settled" : "text-graphite"}>{job.payment_verified ? "Yes, recorded once" : "Not yet"}</dd>
        </div>
      </dl>
    </article>
  );
}

export function JobsView({ jobs, sellerName, loading }: { jobs: JobSummary[] | undefined; sellerName: (id: string) => string; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterId>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLSpanElement>(null);

  const options = useMemo(() => {
    const all = jobs ?? [];
    const n = (f: FilterId) => all.filter((j) => matches(j, f)).length;
    return [
      { id: "all" as const, label: "All", count: all.length },
      { id: "open" as const, label: "In progress", count: n("open") },
      { id: "settled" as const, label: "Settled", count: n("settled") },
      { id: "broken" as const, label: "Failed", count: n("broken") },
    ];
  }, [jobs]);

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (jobs ?? []).filter(
      (j) => matches(j, filter) && (!q || `${j.job_id} ${j.task_id} ${j.capability} ${j.payment_hash} ${j.seller_id}`.toLowerCase().includes(q)),
    );
  }, [jobs, query, filter]);

  useEffect(() => {
    if (list.length && !list.some((j) => j.job_id === selectedId)) setSelectedId(list[0]!.job_id);
  }, [list, selectedId]);

  // Rows deal in when the filter changes.
  useLayoutEffect(() => {
    const rows = scroller.current?.querySelectorAll<HTMLElement>("[data-row]");
    if (!rows?.length || prefersReducedMotion()) return;
    const first = Array.from(rows).slice(0, 18);
    gsap.fromTo(first, { y: 10, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.45, ease: "power3.out", stagger: 0.022, clearProps: "transform,opacity,visibility" });
  }, [filter]);

  // One ink marker slides to the selected row.
  useLayoutEffect(() => {
    const row = scroller.current?.querySelector<HTMLElement>(`[data-row="${selectedId}"]`);
    if (!bar.current) return;
    if (!row) return void gsap.set(bar.current, { autoAlpha: 0 });
    const vars = { y: row.offsetTop, height: row.offsetHeight, autoAlpha: 1 };
    if (prefersReducedMotion()) gsap.set(bar.current, vars);
    else gsap.to(bar.current, { ...vars, duration: 0.45, ease: "power3.inOut" });
  }, [selectedId, list]);

  const selected = list.find((j) => j.job_id === selectedId) ?? null;

  if (loading && jobs === undefined) return <EmptyNote>Loading jobs from the registry.</EmptyNote>;
  if (!jobs?.length) return <EmptyNote>No jobs yet. Run a job from the top bar, or point a buyer agent at this registry.</EmptyNote>;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_480px]">
      <section className="glass min-w-0 self-start overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-rule px-4 py-3">
          <label className="flex min-w-[220px] flex-1 items-center gap-2 rounded-[6px] border border-rule-strong bg-paper/60 px-3 transition-colors focus-within:border-ink focus-within:bg-sheet">
            <Search className="size-4 text-graphite" aria-hidden />
            <span className="sr-only">Search jobs</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by job, task, hash or seller"
              className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-graphite"
            />
          </label>
          <Segmented label="Filter by status" options={options} value={filter} onChange={setFilter} />
        </div>
        {list.length === 0 ? (
          <div className="px-4">
            <EmptyNote>No jobs match. Clear the search or pick another filter.</EmptyNote>
          </div>
        ) : (
          <div ref={scroller} className="relative max-h-[760px] overflow-y-auto" data-lenis-prevent>
            <span ref={bar} className="pointer-events-none absolute left-0 top-0 z-20 w-[3px] rounded-r-full bg-ink opacity-0" aria-hidden />
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-sheet/95 text-left text-2xs text-graphite backdrop-blur">
                <tr className="border-b border-rule">
                  <th className="py-2 pl-4 pr-3 font-medium">Job</th>
                  <th className="hidden px-3 py-2 font-medium md:table-cell">Seller</th>
                  <th className="px-3 py-2 text-right font-medium">Sats</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="hidden py-2 pl-3 pr-4 text-right font-medium sm:table-cell">Posted</th>
                </tr>
              </thead>
              <tbody>
                {list.map((j) => {
                  const on = j.job_id === selectedId;
                  return (
                    <tr
                      key={j.job_id}
                      data-row={j.job_id}
                      onClick={() => setSelectedId(j.job_id)}
                      className={cn("muhr-row cursor-pointer border-b border-rule/70 last:border-0", on && "bg-ink/[0.045]")}
                    >
                      <td className="py-2.5 pl-4 pr-3">
                        <button type="button" className="text-left font-medium outline-offset-4" onClick={() => setSelectedId(j.job_id)} aria-pressed={on}>
                          {capabilityLabel(j.capability)}
                        </button>
                        <span className="hash block text-2xs text-graphite">{shortHash(j.job_id, 12, 4)}</span>
                      </td>
                      <td className="hidden px-3 py-2.5 text-ink-soft md:table-cell">{sellerName(j.seller_id)}</td>
                      <td className="num px-3 py-2.5 text-right font-medium">{sats(j.accepted_price_sats ?? j.budget_sats)}</td>
                      <td className="px-3 py-2.5">
                        <StatusMark status={j.status} />
                      </td>
                      <td className="num hidden whitespace-nowrap py-2.5 pl-3 pr-4 text-right text-xs text-graphite sm:table-cell">
                        {relativeTime(j.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="xl:sticky xl:top-24 xl:self-start">{selected ? <JobDetail key={selected.job_id} job={selected} sellerName={sellerName(selected.seller_id)} /> : null}</div>
    </div>
  );
}
