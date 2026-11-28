import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useMuhrRegistry } from "@/hooks/useMuhrRegistry";
import { useRegistryFeed } from "@/hooks/useRegistryFeed";
import { useRates } from "@/hooks/useRates";
import { formatPkr } from "@/lib/pkr";
import { buildHtlcFromJobs, buildProviderMix, buildVolumeFromJobs } from "@/lib/chartData";
import { capabilityLabel, latestJobTrack, sats } from "@/lib/format";
import { formatApiError, getDemoHealth, runDemoE2E } from "@/lib/muhrApi";
import type { BuyerWalletStatus, DemoHealthResponse, DemoRunResponse } from "@/types/api";
import { SealMark } from "@/components/muhr/primitives";
import { OverviewView } from "@/components/muhr/OverviewView";
import { JobsView } from "@/components/muhr/JobsView";
import { SellersView } from "@/components/muhr/SellersView";
import { VolumeView } from "@/components/muhr/VolumeView";
import { RunJobDialog } from "@/components/muhr/RunJobDialog";
import { PitchView } from "@/components/muhr/PitchView";
import type { PitchPreset } from "@/lib/pitch";
import { KineticHeadline } from "@/components/muhr/KineticHeadline";
import { gsap, prefersReducedMotion, ScrollTrigger, scrollToEl, scrollToTop, useSmoothScroll } from "@/lib/motion";

type View = "overview" | "jobs" | "sellers" | "volume";

const NAV: { id: View; label: string; title: string; blurb: string }[] = [
  { id: "overview", label: "Overview", title: "Overview", blurb: "" },
  { id: "jobs", label: "Jobs", title: "Jobs", blurb: "Every job the registry has seen, with what each seller committed to and how it was paid." },
  { id: "sellers", label: "Sellers", title: "Sellers", blurb: "Agents selling one capability each, at a posted price, with stake behind their work." },
  { id: "volume", label: "Volume", title: "Volume", blurb: "What has been paid, where it went, and how much of it was real Lightning." },
];

const DEMO_WALLET_START_SATS = 5_000;

function readView(): View {
  const h = window.location.hash.replace("#", "");
  return (NAV.some((n) => n.id === h) ? h : "overview") as View;
}

function Notice({ tone, children }: { tone: "warn" | "bad"; children: React.ReactNode }) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[4px] border-l-[3px] px-4 py-2.5 text-sm",
        tone === "warn" ? "border-pending bg-pending-tint text-ink" : "border-seal bg-seal-tint text-ink",
      )}
    >
      {children}
    </div>
  );
}

export default function Index() {
  const [view, setView] = useState<View>(readView);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DemoRunResponse | null>(null);
  const [demoHealth, setDemoHealth] = useState<DemoHealthResponse | null>(null);
  // Pitch mode: ?pitch=1, or press P. Nothing is stored; a reload goes back to what the URL says.
  const [pitch, setPitch] = useState(() => new URLSearchParams(window.location.search).get("pitch") === "1");
  const [pitchError, setPitchError] = useState<string | null>(null);

  const { health, stats, sellers, jobs, isLoading, hasError, refetch, demoMode, buyerWallet } = useMuhrRegistry({ jobsLimit: 200 });
  const { events, status: feedStatus, reconnects } = useRegistryFeed();
  const { rates } = useRates();

  useEffect(() => {
    const onHash = () => {
      setView(readView());
      scrollToTop();
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (v: View) => {
    window.location.hash = v === "overview" ? "" : v;
    setView(v);
    scrollToTop();
  };

  useSmoothScroll(!pitch);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "p" || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      setPitch((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Header tightens once the page is scrolled.
  const headerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const on = () => headerRef.current?.setAttribute("data-scrolled", String(window.scrollY > 12));
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  // One nav underline that slides to the active tab.
  const navRef = useRef<HTMLUListElement>(null);
  const barRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const place = (animate: boolean) => {
      const btn = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
      if (!btn || !barRef.current) return;
      const vars = { x: btn.offsetLeft + 12, width: btn.offsetWidth - 24 };
      if (animate && !prefersReducedMotion()) gsap.to(barRef.current, { ...vars, duration: 0.55, ease: "power3.inOut" });
      else gsap.set(barRef.current, vars);
    };
    place(true);
    const onResize = () => place(false);
    window.addEventListener("resize", onResize);
    void document.fonts?.ready.then(() => place(false));
    return () => window.removeEventListener("resize", onResize);
  }, [view]);

  useEffect(() => {
    void getDemoHealth()
      .then(setDemoHealth)
      .catch(() => setDemoHealth(null));
  }, []);

  // When the ledger moves, pull fresh rows so the line and tables agree with it.
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;
  useEffect(() => {
    if (!events.length) return;
    const t = setTimeout(() => refetchRef.current(), 500);
    return () => clearTimeout(t);
  }, [events.length]);

  // Page change: the new view rises into place, and scroll-driven effects re-measure.
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = mainRef.current?.querySelector<HTMLElement>("[data-view]");
    if (el && !prefersReducedMotion()) {
      gsap.fromTo(el, { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: 0.6, ease: "power3.out", clearProps: "transform,opacity,visibility" });
    }
    const t = setTimeout(() => ScrollTrigger.refresh(), 120);
    return () => clearTimeout(t);
  }, [view]);

  const track = useMemo(() => latestJobTrack(events, jobs), [events, jobs]);
  const volumeData = useMemo(() => buildVolumeFromJobs(jobs), [jobs]);
  const htlcData = useMemo(() => buildHtlcFromJobs(jobs), [jobs]);
  const providerData = useMemo(() => buildProviderMix(jobs, sellers), [jobs, sellers]);

  const lastPaid = useMemo(() => {
    const row = (jobs ?? []).find((j) => j.lightning_payment_hash);
    return row?.lightning_payment_hash
      ? { hash: row.lightning_payment_hash, amount: row.accepted_price_sats ?? row.budget_sats, mode: row.lightning_mode ?? "DEMO" }
      : null;
  }, [jobs]);

  const demoPaid = useMemo(() => events.reduce((t, e) => (e.type === "lightning_paid" ? t + (e.amount_sats ?? 0) : t), 0), [events]);

  const wallet = useMemo((): BuyerWalletStatus | undefined => {
    if (buyerWallet?.available && buyerWallet.mode.toUpperCase() === "REAL") return buyerWallet;
    return {
      available: false,
      mode: "DEMO",
      balance_sats: Math.max(0, DEMO_WALLET_START_SATS - demoPaid),
      network: null,
      pubkey: null,
      generated_at: new Date().toISOString(),
    };
  }, [buyerWallet, demoPaid]);

  const sellerName = useCallback(
    (id: string) => {
      const s = sellers?.find((x) => x.seller_id === id);
      return s ? capabilityLabel(s.capability) : id;
    },
    [sellers],
  );

  const runJob = useCallback(
    async ({ text, sellerId, budget }: { text: string; sellerId: string; budget: number }) => {
      if (busy) return;
      setBusy(true);
      setDialogOpen(false);
      go("overview");
      try {
        const r = await runDemoE2E({ input_text: text, seller_id: sellerId, budget_sats: budget });
        setResult(r);
        // The result card is far down the Overview page: bring it into view once it has rendered.
        let tries = 0;
        const bringIntoView = () => {
          const el = document.querySelector('[aria-label="Your last result"]');
          if (el) scrollToEl(el, -90);
          else if (tries++ < 30) window.setTimeout(bringIntoView, 100);
        };
        window.setTimeout(bringIntoView, 300);
        toast.success("Job settled", { description: `${sats(r.budget_sats)} sats${rates ? ` (about ${formatPkr(r.budget_sats, rates.sats_pkr)})` : ""} paid to ${sellerName(r.seller_id)}. The result is below.` });
        refetch();
      } catch (e) {
        toast.error("The job didn't finish", { description: formatApiError(e, { ifAbort: "longDemo" }).slice(0, 400) });
      } finally {
        setBusy(false);
      }
    },
    [busy, refetch, sellerName, rates],
  );

  const runPreset = useCallback(
    async (p: PitchPreset) => {
      if (busy) return;
      setBusy(true);
      setPitchError(null);
      setResult(null);
      try {
        setResult(await runDemoE2E({ input_text: p.text, seller_id: p.sellerId, budget_sats: p.budget }));
        refetch();
      } catch (e) {
        setPitchError(formatApiError(e, { ifAbort: "longDemo" }).slice(0, 300));
      } finally {
        setBusy(false);
      }
    },
    [busy, refetch],
  );

  const healthy = health?.status === "healthy";
  const connection =
    health == null && isLoading
      ? { text: "Connecting", dot: "bg-graphite" }
      : !healthy
        ? { text: "Registry offline", dot: "bg-seal" }
        : feedStatus === "open"
          ? { text: demoMode ? "Live, demo mode" : "Live, real Lightning", dot: "bg-settled" }
          : { text: "Feed reconnecting", dot: "bg-pending" };

  const current = NAV.find((n) => n.id === view)!;

  if (pitch) {
    return (
      <PitchView
        events={events}
        feedStatus={feedStatus}
        jobs={jobs}
        demoMode={demoMode}
        busy={busy}
        result={result}
        error={pitchError}
        onRun={(p) => void runPreset(p)}
        onExit={() => setPitch(false)}
      />
    );
  }

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-ink focus:px-3 focus:py-2 focus:text-sheet">
        Skip to content
      </a>
      <header ref={headerRef} className="muhr-header glass-bar sticky top-0 z-40">
        <div className="muhr-header-row mx-auto flex h-[4.25rem] max-w-[1240px] items-center gap-8 px-4 sm:px-6">
          <button type="button" onClick={() => go("overview")} className="group flex shrink-0 items-center gap-2.5" aria-label="Muhr, overview">
            <SealMark className="size-7 transition-transform duration-500 ease-[cubic-bezier(.3,1.6,.5,1)] group-hover:rotate-[-18deg] group-hover:scale-110" />
            <span className="type-wide text-xl font-extrabold">Muhr</span>
          </button>
          <nav aria-label="Sections" className="hidden h-full md:block">
            <ul ref={navRef} className="relative flex h-full items-stretch gap-1">
              <span ref={barRef} className="absolute -bottom-px left-0 h-[2px] w-0 rounded-full bg-ink" aria-hidden />
              {NAV.map((n) => (
                <li key={n.id} className="flex">
                  <button
                    type="button"
                    onClick={() => go(n.id)}
                    aria-current={view === n.id ? "page" : undefined}
                    className={cn(
                      "relative px-3 text-sm font-medium transition-colors",
                      view === n.id ? "text-ink" : "text-graphite hover:text-ink",
                    )}
                  >
                    {n.label}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <span className="hidden items-center gap-2 text-xs text-graphite sm:flex">
              <span className={cn("size-2 rounded-full", connection.dot)} aria-hidden />
              {connection.text}
            </span>
            <span className="inline-block">
              <Button variant="seal" type="button" className="muhr-arrow" onClick={() => setDialogOpen(true)} disabled={busy}>
                {busy ? <span className="muhr-busy" aria-hidden /> : null}
                {busy ? "Job running…" : "Run a job"}
                {busy ? null : <ArrowRight />}
              </Button>
            </span>
          </div>
        </div>
        <nav aria-label="Sections" className="border-t border-rule md:hidden">
          <ul className="mx-auto flex max-w-[1240px] px-2">
            {NAV.map((n) => (
              <li key={n.id} className="flex-1">
                <button
                  type="button"
                  onClick={() => go(n.id)}
                  aria-current={view === n.id ? "page" : undefined}
                  className={cn(
                    "relative w-full py-2.5 text-sm font-medium",
                    view === n.id ? "text-ink" : "text-graphite",
                  )}
                >
                  {n.label}
                  {view === n.id ? <span className="muhr-underline absolute inset-x-4 -bottom-px h-[2px] bg-ink" aria-hidden /> : null}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main id="main" ref={mainRef} className="mx-auto max-w-[1240px] px-4 pb-20 pt-6 sm:px-6">
        <div className="space-y-2 empty:hidden">
          {hasError ? (
            <Notice tone="bad">
              <span>The registry isn&rsquo;t answering. Start it on port 8000, or set VITE_API_BASE_URL to where it runs.</span>
              <Button size="sm" variant="outline" onClick={refetch}>
                Try again
              </Button>
            </Notice>
          ) : feedStatus === "error" ? (
            <Notice tone="warn">
              The live ledger dropped and is reconnecting{reconnects > 1 ? ` (attempt ${reconnects})` : ""}. Tables still refresh on their own.
            </Notice>
          ) : null}
          {!hasError && demoHealth && !demoHealth.summarizer_ok ? (
            <Notice tone="warn">
              <span>
                The summarizer at <span className="hash">{demoHealth.summarizer_url}</span> isn&rsquo;t reachable, so demo jobs will fail. Start it from
                the repo root with <code className="hash rounded bg-sheet px-1.5 py-0.5">start_sellers.bat</code>.
              </span>
            </Notice>
          ) : null}
        </div>

        {view !== "overview" ? (
          <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-3 pb-8 pt-8">
            <KineticHeadline
              key={current.id}
              text={current.title}
              interactive={false}
              className="text-[2.8rem] font-extrabold leading-[0.95] tracking-[-0.02em] sm:text-[3.6rem]"
            />
            <p key={`${current.id}-blurb`} className="muhr-fade-in max-w-[46ch] pb-1 text-[0.95rem] leading-relaxed text-ink-soft">
              {current.blurb}
            </p>
          </div>
        ) : null}

        <div data-view key={view}>
        {view === "overview" && (
          <OverviewView
            stats={stats}
            sellers={sellers}
            jobs={jobs}
            volumeData={volumeData}
            htlcData={htlcData}
            events={events}
            feedStatus={feedStatus}
            track={track}
            wallet={wallet}
            lastPaid={lastPaid}
            result={result}
            onRun={() => setDialogOpen(true)}
            loading={isLoading}
          />
        )}
        {view === "jobs" && <JobsView jobs={jobs} sellerName={sellerName} loading={isLoading} />}
        {view === "sellers" && <SellersView sellers={sellers} loading={isLoading} error={hasError} onRetry={refetch} />}
        {view === "volume" && (
          <VolumeView stats={stats} volumeData={volumeData} providerData={providerData} htlcData={htlcData} loading={isLoading} />
        )}
        </div>
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-[1240px] flex-wrap justify-between gap-2 px-4 py-6 text-xs text-graphite sm:px-6">
          <span>
            Muhr protocol. Sealed input, committed results, payment-released keys. Built in Pakistan.{" "}
            <span className="whitespace-nowrap">
              Muhr (<span lang="ur" dir="rtl" className="font-urdu">مہر</span>) means seal.
            </span>
          </span>
          <span>{stats ? `Updated ${new Date(stats.generated_at).toLocaleTimeString("en-GB")}` : null}</span>
        </div>
      </footer>

      <RunJobDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        sellers={sellers}
        busy={busy}
        onRun={(a) => void runJob(a)}
        sellerReachable={demoHealth ? demoHealth.summarizer_ok : null}
      />
    </div>
  );
}
