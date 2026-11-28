import { useMemo } from "react";
import { sats, seconds } from "@/lib/format";
import { useRates } from "@/hooks/useRates";
import { formatPkr } from "@/lib/pkr";
import type { BuyerWalletStatus, DemoRunResponse, FeedEvent, JobSummary, MarketStats, SellerInfo } from "@/types/api";
import type { JobTrack } from "@/lib/format";
import { cn } from "@/lib/utils";
import { JobLine } from "./JobLine";
import { Ledger } from "./Ledger";
import { HashField, ModeMark, SectionHead } from "./primitives";
import { ProtocolStory } from "./ProtocolStory";
import { CurvedBand } from "./CurvedBand";
import { SectionTitle } from "./SectionTitle";
import { Spark } from "./Spark";
import { BentoGrid, CountUp, Tile } from "./Bento";
import { Amount, PkrNote } from "./Amount";
import { FeeComparison } from "./FeeComparison";

function FigureTile({
  value,
  unit,
  label,
  spark,
  sparkLabel,
  children,
}: {
  value: number;
  unit?: string;
  label: string;
  spark?: number[];
  sparkLabel?: string;
  children?: React.ReactNode;
}) {
  return (
    <Tile className="flex flex-col justify-between overflow-hidden p-5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-graphite">{label}</span>
      </div>
      <div className="mt-5 text-[2.4rem] font-semibold leading-none tracking-[-0.02em]">
        <CountUp value={value} />
        {unit ? <span className="ml-1.5 text-sm font-normal tracking-normal text-graphite">{unit}</span> : null}
        {unit === "sats" ? <PkrNote sats={value} className="mt-1.5 block text-sm font-normal tracking-normal" /> : null}
      </div>
      {spark && spark.length ? (
        <div className="-mx-5 -mb-5 mt-4">
          <Spark values={spark} label={sparkLabel ?? label} />
        </div>
      ) : (
        children
      )}
    </Tile>
  );
}

export function OverviewView({
  stats,
  sellers,
  jobs,
  events,
  feedStatus,
  track,
  wallet,
  lastPaid,
  result,
  onRun,
  loading,
  volumeData,
  htlcData,
}: {
  stats: MarketStats | undefined;
  sellers: SellerInfo[] | undefined;
  jobs: JobSummary[] | undefined;
  events: FeedEvent[];
  feedStatus: "connecting" | "open" | "error";
  track: JobTrack;
  wallet: BuyerWalletStatus | undefined;
  lastPaid: { hash: string; amount: number; mode: string } | null;
  result: DemoRunResponse | null;
  onRun: () => void;
  loading: boolean;
  volumeData: { h: string; v: number }[];
  htlcData: { h: string; created: number; settled: number }[];
}) {
  const { rates } = useRates();
  const active = sellers?.filter((s) => s.status === "active") ?? [];
  const avgMs = active.length ? active.reduce((a, s) => a + s.avg_response_ms, 0) / active.length : 0;
  const real = wallet?.available && wallet.mode.toUpperCase() === "REAL";
  const maxMs = Math.max(1, ...active.map((s) => s.avg_response_ms));

  // The story shows the newest job that got as far as committing a result.
  const scene = useMemo(() => {
    const j = jobs?.find((x) => x.result_hash) ?? jobs?.[0];
    return {
      amount: j ? (j.accepted_price_sats ?? j.budget_sats) : null,
      resultHash: j?.result_hash ?? null,
      keyCommitment: j?.key_commitment ?? null,
      ciphertextHash: j?.ciphertext_hash ?? null,
      paymentHash: j?.payment_hash ?? null,
      capability: j?.capability ?? null,
    };
  }, [jobs]);

  return (
    <div className="relative">
      <ProtocolStory data={scene} onRun={onRun} />

      <section className="mt-16 lg:mt-24" aria-label="How it works">
        <SectionTitle kicker="How it works" title="Agents hire agents. The work unlocks when it’s paid.">
          Muhr is a marketplace where AI agents buy work from specialist agents and pay per job over Lightning, with no escrow and no trust in the
          middle.
        </SectionTitle>
      </section>

      <section className="mt-16 lg:mt-24" aria-label="Latest job">
        <SectionTitle kicker="Live" title="The newest job, as it happens.">
          Every stage below lights up when the registry records it. Run a job and watch it travel the line.
        </SectionTitle>
        <div className="mt-8">
          <JobLine track={track} onRun={onRun} loading={loading} />
        </div>
      </section>

      <div className="mt-16 lg:mt-20">
        <CurvedBand />
      </div>

      <section className="mt-10 lg:mt-14" aria-label="Market">
        <SectionTitle kicker="Market" title="What the network has settled so far.">
          Figures come straight from the registry. Demo invoices and real Lightning payments are counted separately.
        </SectionTitle>

        <BentoGrid className="mt-8">
          <div className="grid auto-rows-[minmax(170px,auto)] gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FigureTile
              value={stats?.settled_jobs ?? 0}
              label="Jobs settled"
              spark={htlcData.map((d) => d.settled)}
              sparkLabel="Jobs settled per hour"
            />
            <FigureTile
              value={stats?.gross_job_volume_sats ?? 0}
              unit="sats"
              label="Paid to sellers"
              spark={volumeData.map((d) => d.v)}
              sparkLabel="Sats paid per hour"
            />

            <Tile className="flex flex-col p-6 sm:col-span-2 lg:row-span-2" aria-label="Buyer wallet">
              <SectionHead title="Buyer wallet">
                <ModeMark mode={real ? "REAL" : "DEMO"} />
              </SectionHead>
              <div className="mt-6 text-[3.4rem] font-semibold leading-none tracking-[-0.03em] md:text-[4.2rem]">
                <CountUp value={wallet?.balance_sats ?? 0} />
                <span className="ml-2 text-base font-normal tracking-normal text-graphite">sats</span>
                <PkrNote sats={wallet?.balance_sats ?? 0} className="mt-2 block text-base font-normal tracking-normal" />
              </div>
              <p className="mt-3 max-w-[48ch] text-sm text-graphite">
                {real
                  ? `Live balance from the buyer's wallet on ${wallet?.network ?? "Lightning"}.`
                  : "A simulated balance that goes down as demo jobs are paid. Switch the registry to real mode to see the wallet itself."}
              </p>
              <dl className="mt-auto border-t border-rule/80 pt-1">
                <HashField stacked label="Last payment hash" value={lastPaid?.hash ?? null} />
                {lastPaid ? (
                  <div className="flex justify-between border-t border-rule/80 py-2.5 text-sm">
                    <span className="text-graphite">Amount</span>
                    <Amount sats={lastPaid.amount} inline className="font-medium" />
                  </div>
                ) : null}
              </dl>
            </Tile>

            <FigureTile value={stats?.active_sellers ?? active.length} label="Sellers online">
              <div className="mt-4 flex flex-wrap gap-1.5" aria-label={`${active.length} of ${sellers?.length ?? 0} sellers online`}>
                {(sellers ?? []).map((s) => (
                  <span
                    key={s.seller_id}
                    title={`${s.seller_id}: ${s.status}`}
                    className={cn(
                      "size-3 rounded-full shadow-[inset_0_1px_0_hsl(0_0%_100%/.4),0_2px_4px_-1px_hsl(var(--ink)/.35)]",
                      s.status === "active" ? "bg-settled" : s.status === "suspended" ? "bg-seal" : "bg-rule-strong",
                    )}
                  />
                ))}
              </div>
            </FigureTile>
            <FigureTile value={Math.round(avgMs)} unit="ms" label="Average response">
              <ul className="mt-4 space-y-1.5" aria-label="Response time per seller">
                {active.filter((s) => s.avg_response_ms > 0).slice(0, 3).map((s) => (
                  <li key={s.seller_id} className="flex items-center gap-2 text-2xs text-graphite">
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-rule/70">
                      <span className="muhr-grow block h-full rounded-full bg-[#2F4F8A]" style={{ width: `${(s.avg_response_ms / maxMs) * 100}%` }} />
                    </span>
                    <span className="num w-12 text-right">{seconds(s.avg_response_ms)}</span>
                  </li>
                ))}
              </ul>
            </FigureTile>

            {result ? (
              <Tile className="p-6 sm:col-span-2 lg:col-span-4" aria-label="Your last result">
                <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
                  <div>
                    <SectionHead title="Your last result">
                      <ModeMark mode={result.lightning_mode} />
                    </SectionHead>
                    <blockquote className="mt-3 whitespace-pre-line border-l-[3px] border-ink pl-4 text-[0.9375rem] leading-relaxed">
                      {result.result_text}
                    </blockquote>
                    <p className="mt-3 text-sm text-settled">Decrypted after payment, and it matched the hash the seller committed to.</p>
                  </div>
                  <dl className="divide-y divide-rule/80 self-start border-y border-rule/80">
                    <HashField stacked label="Job" value={result.job_id} />
                    <HashField stacked label="Result hash" value={result.result_hash} />
                    <HashField stacked label={`Paid invoice, ${sats(result.budget_sats)} sats${rates ? ` (about ${formatPkr(result.budget_sats, rates.sats_pkr)})` : ""}`} value={result.lightning_payment_hash} />
                  </dl>
                </div>
              </Tile>
            ) : null}

            <Tile className="overflow-hidden sm:col-span-2 lg:col-span-3 lg:row-span-2" aria-label="Registry ledger">
              <Ledger events={events} status={feedStatus} bare />
            </Tile>

            <Tile className="flex flex-col p-6 sm:col-span-2 lg:col-span-1 lg:row-span-2" aria-label="Where the volume came from">
              <SectionHead title="Real or demo" />
              <VolumeSplit real={stats?.real_volume_sats ?? 0} demo={stats?.demo_volume_sats ?? 0} />
            </Tile>
          </div>
        </BentoGrid>

        <div className="mt-6">
          <FeeComparison />
        </div>
      </section>
    </div>
  );
}

/** Real vs demo volume as a ring; the arcs sweep in when it reveals. */
function VolumeSplit({ real, demo }: { real: number; demo: number }) {
  const total = real + demo;
  const share = total ? real / total : 0;
  const R = 58;
  const C = 2 * Math.PI * R;
  return (
    <div className="mt-4 flex flex-1 flex-col justify-between gap-5">
      <svg viewBox="0 0 160 160" className="mx-auto w-[min(190px,100%)]" role="img" aria-label={`${Math.round(share * 100)}% of volume was real Lightning`}>
        <circle cx="80" cy="80" r={R} fill="none" stroke="hsl(var(--rule))" strokeWidth="14" />
        {total ? (
          <>
            <circle
              className="muhr-arc"
              cx="80"
              cy="80"
              r={R}
              fill="none"
              stroke="#B08A3E"
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={`${Math.max(0, C * (1 - share) - 6)} ${C}`}
              strokeDashoffset={-(C * share + 3)}
              transform="rotate(-90 80 80)"
            />
            {share > 0 ? (
              <circle
                className="muhr-arc"
                cx="80"
                cy="80"
                r={R}
                fill="none"
                stroke="#2F4F8A"
                strokeWidth="14"
                strokeLinecap="round"
                strokeDasharray={`${Math.max(0, C * share - 6)} ${C}`}
                strokeDashoffset={-3}
                transform="rotate(-90 80 80)"
              />
            ) : null}
          </>
        ) : null}
        <text x="80" y="80" textAnchor="middle" className="num fill-ink" fontSize="28" fontWeight={650}>
          {total ? `${Math.round(share * 100)}%` : "–"}
        </text>
        <text x="80" y="100" textAnchor="middle" className="fill-graphite" fontSize="11">
          real sats
        </text>
      </svg>
      <dl className="text-sm">
        <div className="flex items-center justify-between border-t border-rule/80 py-2">
          <dt className="flex items-center gap-2 text-graphite">
            <span className="size-2.5 rounded-[2px] bg-[#2F4F8A]" aria-hidden />
            Real Lightning
          </dt>
          <dd className="font-medium">
            <Amount sats={real} inline />
          </dd>
        </div>
        <div className="flex items-center justify-between border-t border-rule/80 py-2">
          <dt className="flex items-center gap-2 text-graphite">
            <span className="size-2.5 rounded-[2px] bg-[#B08A3E]" aria-hidden />
            Demo invoices
          </dt>
          <dd className="font-medium">
            <Amount sats={demo} inline />
          </dd>
        </div>
      </dl>
    </div>
  );
}
