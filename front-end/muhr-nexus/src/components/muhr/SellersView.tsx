import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { capabilityLabel, relativeTime, sats, seconds } from "@/lib/format";
import { Flip, gsap, prefersReducedMotion } from "@/lib/motion";
import type { SellerInfo } from "@/types/api";
import { EmptyNote } from "./primitives";
import { BentoGrid, CountUp, Tile } from "./Bento";
import { Segmented } from "./Segmented";

const REGISTER_CURL = `curl -X POST http://127.0.0.1:8000/api/sellers/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "lightning_pubkey": "02…your node pubkey",
    "capability": "text_summarization",
    "price_sats_per_unit": 10,
    "unit_definition": "per 1000 tokens",
    "endpoint_url": "https://seller.example.com",
    "commitment_endpoint": "https://seller.example.com/commit",
    "docker_image_hash": "sha256:<64 hex chars of your image digest>"
  }'`;

const sellerStatus: Record<string, { label: string; text: string; dot: string }> = {
  active: { label: "Online", text: "text-settled", dot: "bg-settled" },
  inactive: { label: "Unreachable", text: "text-pending", dot: "bg-pending" },
  suspended: { label: "Suspended", text: "text-seal", dot: "bg-seal" },
};

type SortId = "reputation" | "price" | "stake" | "jobs";
const SORTS = [
  { id: "reputation", label: "Reputation" },
  { id: "jobs", label: "Jobs" },
  { id: "stake", label: "Stake" },
  { id: "price", label: "Price" },
] as const satisfies readonly { id: SortId; label: string }[];

const sorters: Record<SortId, (a: SellerInfo, b: SellerInfo) => number> = {
  reputation: (a, b) => b.reputation_score - a.reputation_score,
  jobs: (a, b) => b.jobs_completed - a.jobs_completed,
  stake: (a, b) => b.stake_sats - a.stake_sats,
  price: (a, b) => a.price_sats_per_unit - b.price_sats_per_unit,
};

function host(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * Reputation as a ring, with what it measures set around it on a text path, the same
 * way the wax seal carries its legend.
 */
function ReputationRing({ score, jobs }: { score: number; jobs: number }) {
  const id = useId().replace(/:/g, "");
  const pct = Math.max(0, Math.min(100, score));
  const R = 40;
  const C = 2 * Math.PI * R;
  const legend = `Reputation  ✦  ${sats(jobs)} ${jobs === 1 ? "job" : "jobs"} delivered  ✦  `;
  return (
    <svg viewBox="0 0 120 120" className="group/ring size-[116px] shrink-0 overflow-visible" role="img" aria-label={`Reputation ${pct.toFixed(0)} out of 100`}>
      <defs>
        <path id={`ring-${id}`} d="M 60 60 m -53 0 a 53 53 0 1 1 106 0 a 53 53 0 1 1 -106 0" />
      </defs>
      <g className="[transform-box:view-box] [transform-origin:60px_60px] transition-transform duration-[1.4s] ease-[cubic-bezier(.2,.7,.2,1)] group-hover/card:rotate-[60deg]">
        <text fontSize="7.4" letterSpacing="1.6" className="fill-graphite" fontWeight={600}>
          <textPath href={`#ring-${id}`} textLength={2 * Math.PI * 53 - 4} lengthAdjust="spacing">
            {legend.repeat(2)}
          </textPath>
        </text>
      </g>
      <circle cx="60" cy="60" r={R} fill="none" stroke="hsl(var(--rule))" strokeWidth="7" />
      {pct > 0 ? (
        <circle
          className="muhr-arc"
          cx="60"
          cy="60"
          r={R}
          fill="none"
          stroke="hsl(var(--ink))"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${(C * pct) / 100} ${C}`}
          transform="rotate(-90 60 60)"
        />
      ) : null}
      <text x="60" y="66" textAnchor="middle" className="num fill-ink" fontSize="22" fontWeight={650}>
        {pct.toFixed(0)}
      </text>
    </svg>
  );
}

/** Stake as a short stack of coins seen edge-on: one more coin per order of magnitude. */
function StakeStack({ stake }: { stake: number }) {
  const n = stake > 0 ? Math.min(7, Math.max(1, Math.round(Math.log10(stake + 1) * 1.4))) : 0;
  return (
    <span className="flex h-[52px] w-[30px] flex-col-reverse items-center" aria-hidden>
      {Array.from({ length: n }, (_, i) => (
        <span key={i} data-coin className="muhr-disc -mt-[1px] shrink-0" style={{ translate: `${(i % 2 ? 1 : -1) * (i % 3)}px 0` }} />
      ))}
    </span>
  );
}

function SellerCard({ s }: { s: SellerInfo }) {
  const st = sellerStatus[s.status] ?? { label: s.status, text: "text-graphite", dot: "bg-graphite" };
  return (
    <div data-card={s.seller_id} className="group/card min-w-0">
      <Tile as="article" className="flex h-full flex-col p-5" aria-label={capabilityLabel(s.capability)}>
        <div className="flex items-center justify-between gap-3">
          <span className={cn("flex items-center gap-2 text-xs font-medium", st.text)}>
            <span className={cn("relative size-2 rounded-full", st.dot, s.status === "active" && "muhr-live")} aria-hidden />
            {st.label}
          </span>
          <span className="text-2xs text-graphite">seen {relativeTime(s.last_seen)}</span>
        </div>

        <h3 className="type-wide mt-4 text-[1.4rem] font-bold leading-tight">{capabilityLabel(s.capability)}</h3>
        <p className="mt-0.5 truncate text-xs text-graphite" title={s.endpoint_url}>
          <span className="hash text-2xs">{s.seller_id}</span> at {host(s.endpoint_url)}
        </p>

        <div className="mt-5 flex items-center gap-5">
          <ReputationRing score={s.reputation_score} jobs={s.jobs_completed} />
          <dl className="min-w-0 flex-1 space-y-3 text-sm">
            <div>
              <dt className="text-xs text-graphite">Price</dt>
              <dd className="mt-0.5">
                <span className="num text-xl font-semibold tracking-tight">{sats(s.price_sats_per_unit)}</span>{" "}
                <span className="text-xs text-graphite">sats {s.unit_definition}</span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-graphite">Response</dt>
              <dd className="num mt-0.5 font-medium">{seconds(s.avg_response_ms)}</dd>
            </div>
          </dl>
        </div>

        <div className="mt-auto flex items-end justify-between gap-3 border-t border-rule/80 pt-3">
          <div>
            <div className="text-xs text-graphite">Stake at risk</div>
            <div className="mt-0.5 text-lg font-semibold tracking-tight">
              <CountUp value={s.stake_sats} /> <span className="text-xs font-normal text-graphite">sats</span>
            </div>
          </div>
          <StakeStack stake={s.stake_sats} />
        </div>
      </Tile>
    </div>
  );
}

function RegisterDialog() {
  const [copied, setCopied] = useState(false);
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" type="button">
          Register a seller
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="type-wide text-xl">Register a seller</DialogTitle>
          <DialogDescription>
            Sellers join through the API. The response includes a seller key, shown once. Send it as <code className="hash">X-Muhr-Seller-Key</code> on
            every seller call. Outside demo mode, stake starts at zero until a verified deposit is credited.
          </DialogDescription>
        </DialogHeader>
        <div className="relative">
          <pre className="hash max-h-[340px] overflow-auto rounded-[6px] border border-rule bg-paper p-4 text-xs leading-relaxed text-ink">{REGISTER_CURL}</pre>
          <button
            type="button"
            onClick={() =>
              void navigator.clipboard?.writeText(REGISTER_CURL).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1200);
              })
            }
            className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-[4px] border border-rule bg-sheet px-2 py-1 text-xs text-graphite hover:text-ink"
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function SellersView({ sellers, loading, error, onRetry }: { sellers: SellerInfo[] | undefined; loading: boolean; error: boolean; onRetry: () => void }) {
  const [sort, setSort] = useState<SortId>("reputation");
  const grid = useRef<HTMLDivElement>(null);
  const flipState = useRef<Flip.FlipState | null>(null);

  const sorted = useMemo(() => (sellers ?? []).slice().sort(sorters[sort]), [sellers, sort]);
  const online = (sellers ?? []).filter((s) => s.status === "active").length;
  const staked = (sellers ?? []).reduce((a, s) => a + s.stake_sats, 0);

  const changeSort = (v: SortId) => {
    if (v === sort) return;
    const cards = grid.current?.querySelectorAll("[data-card]");
    if (cards?.length && !prefersReducedMotion()) flipState.current = Flip.getState(cards);
    setSort(v);
  };

  // Cards travel to their new places when the order changes.
  useLayoutEffect(() => {
    const state = flipState.current;
    if (!state) return;
    flipState.current = null;
    Flip.from(state, { duration: 0.7, ease: "power3.inOut", stagger: 0.03, absolute: false });
  }, [sort]);

  // Coins drop onto the stacks once, when the roster first shows.
  useLayoutEffect(() => {
    const el = grid.current;
    if (!el || prefersReducedMotion()) return;
    const coins = el.querySelectorAll("[data-coin]");
    if (!coins.length) return;
    const tween = gsap.fromTo(coins, { y: -26, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.5, ease: "bounce.out", stagger: 0.05, delay: 0.5 });
    return () => {
      tween.kill();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(sellers?.length)]);

  return (
    <div className="space-y-6">
      {loading && !sellers ? (
        <EmptyNote>Loading the seller directory.</EmptyNote>
      ) : error && !sellers ? (
        <EmptyNote
          action={
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          }
        >
          The registry didn&rsquo;t answer. Check that it&rsquo;s running on port 8000.
        </EmptyNote>
      ) : !sellers?.length ? (
        <EmptyNote action={<RegisterDialog />}>No sellers are listed. Start the built-in sellers, or register one through the API.</EmptyNote>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-sm text-ink-soft">
              <span className="num font-semibold text-ink">{online}</span> of <span className="num">{sellers.length}</span> online, with{" "}
              <span className="num font-semibold text-ink">{sats(staked)}</span> sats staked between them. A proven bad result costs a seller half its
              stake.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Segmented label="Sort sellers" options={SORTS} value={sort} onChange={changeSort} />
              <RegisterDialog />
            </div>
          </div>

          <BentoGrid>
            <div ref={grid} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {sorted.map((s) => (
                <SellerCard key={s.seller_id} s={s} />
              ))}
            </div>
          </BentoGrid>
        </>
      )}
    </div>
  );
}
