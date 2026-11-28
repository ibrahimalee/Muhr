import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QRCode from "qrcode";
import { ArrowLeft, Printer, ShieldCheck, ShieldAlert, ShieldQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_CONFIG } from "@/config/api";
import { capabilityLabel } from "@/lib/format";
import { getReceipt } from "@/lib/muhrApi";
import { receiptUrl, verifyReceipt, type ReceiptCheck } from "@/lib/receipt";
import { cn } from "@/lib/utils";
import { Amount } from "@/components/muhr/Amount";
import { HashField, ModeMark, SealMark } from "@/components/muhr/primitives";
import { WaxSeal } from "@/components/muhr/WaxSeal";

function stamp(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "–"
    : d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function useQr(url: string): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    QRCode.toString(url, { type: "svg", margin: 1, width: 148, color: { dark: "#151b2f", light: "#ffffff" } })
      .then((svg) => live && setSrc(`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`))
      .catch(() => live && setSrc(null));
    return () => {
      live = false;
    };
  }, [url]);
  return src;
}

function Verdict({ check }: { check: ReceiptCheck }) {
  if (check.state === "verified")
    return (
      <div role="status" className="flex items-start gap-3 rounded-[6px] border border-settled/40 bg-settled-tint px-4 py-3 text-settled">
        <ShieldCheck className="mt-0.5 size-6 shrink-0" aria-hidden />
        <div>
          <div className="font-semibold">Verified</div>
          <p className="text-sm">sha256 of the preimage equals the payment hash, so the payment was really made. Checked in your browser.</p>
        </div>
      </div>
    );
  if (check.state === "mismatch")
    return (
      <div role="alert" className="flex items-start gap-3 rounded-[6px] border border-seal/50 bg-seal-tint px-4 py-3 text-seal">
        <ShieldAlert className="mt-0.5 size-6 shrink-0" aria-hidden />
        <div>
          <div className="font-semibold">Mismatch</div>
          <p className="text-sm">
            sha256 of the preimage does not equal the payment hash, so this receipt does not prove payment. It computed{" "}
            <span className="hash break-all">{check.computed}</span>.
          </p>
        </div>
      </div>
    );
  if (check.state === "malformed")
    return (
      <div role="alert" className="flex items-start gap-3 rounded-[6px] border border-seal/50 bg-seal-tint px-4 py-3 text-seal">
        <ShieldAlert className="mt-0.5 size-6 shrink-0" aria-hidden />
        <div>
          <div className="font-semibold">Mismatch</div>
          <p className="text-sm">The preimage or payment hash on this receipt is not a 32-byte hex value, so it cannot be checked.</p>
        </div>
      </div>
    );
  return (
    <div role="status" className="flex items-start gap-3 rounded-[6px] border border-rule-strong bg-secondary px-4 py-3 text-ink">
      <ShieldQuestion className="mt-0.5 size-6 shrink-0 text-graphite" aria-hidden />
      <div>
        <div className="font-semibold">No preimage on this receipt</div>
        <p className="text-sm text-ink-soft">
          Payment on this job was confirmed by the seller&rsquo;s wallet instead of a preimage, so there is nothing to hash here. The hashes below are
          the ones the seller committed before it was paid.
        </p>
      </div>
    </div>
  );
}

export default function Receipt() {
  const { jobId = "" } = useParams();
  const url = receiptUrl(jobId);
  const qr = useQr(url);
  const [check, setCheck] = useState<ReceiptCheck | null>(null);
  const q = useQuery({
    queryKey: [API_CONFIG.BASE_URL, "receipt", jobId],
    queryFn: () => getReceipt(jobId),
    enabled: Boolean(jobId),
    retry: false,
  });
  const r = q.data;

  useEffect(() => setCheck(null), [jobId]);

  const verify = async () => {
    if (!r) return;
    setCheck(await verifyReceipt(r));
  };

  const err = q.error as { statusCode?: number; message?: string } | null;

  return (
    <div className="min-h-screen">
      <header className="no-print border-b border-rule">
        <div className="mx-auto flex h-16 max-w-[880px] items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5" aria-label="Muhr, home">
            <SealMark className="size-7" />
            <span className="type-wide text-xl font-extrabold">Muhr</span>
          </Link>
          <Link to="/#jobs" className="inline-flex items-center gap-1.5 text-sm text-graphite hover:text-ink">
            <ArrowLeft className="size-4" aria-hidden /> Back to jobs
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-[880px] px-4 pb-16 pt-8 sm:px-6">
        {q.isPending ? (
          <p className="py-16 text-center text-graphite" role="status">
            Loading receipt…
          </p>
        ) : q.isError || !r ? (
          <div role="alert" className="mx-auto max-w-[46ch] py-16 text-center">
            <h1 className="type-wide text-2xl font-bold">{err?.statusCode === 404 ? "No such job" : err?.statusCode === 409 ? "Not settled yet" : "Receipt unavailable"}</h1>
            <p className="mt-2 text-graphite">
              {err?.statusCode === 404
                ? "The registry has no job with this ID."
                : err?.statusCode === 409
                  ? "A receipt is issued once a job is settled. Check back after payment."
                  : "The registry could not be reached. Try again in a moment."}
            </p>
            <Button className="mt-6" variant="outline" onClick={() => void q.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <article className="glass relative overflow-hidden p-6 sm:p-10 print:shadow-none" aria-label={`Receipt for job ${r.job_id}`}>
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-seal">Muhr receipt</div>
                <h1 className="type-wide mt-2 text-[2rem] font-extrabold leading-tight sm:text-[2.6rem]">{capabilityLabel(r.capability)}</h1>
                <p className="mt-1 text-sm text-graphite">
                  Sold by <span className="hash">{r.seller_id}</span>
                </p>
              </div>
              <WaxSeal className="size-28 shrink-0 sm:size-32" />
            </div>

            <dl className="mt-8 grid gap-x-8 gap-y-5 border-y border-rule py-6 sm:grid-cols-3">
              <div>
                <dt className="text-xs text-graphite">Paid</dt>
                <dd className="mt-1 text-2xl font-semibold">
                  <Amount sats={r.price_sats} pkrClassName="text-sm" />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-graphite">Platform fee</dt>
                <dd className="mt-1 text-2xl font-semibold">
                  <Amount sats={r.platform_fee_sats} pkrClassName="text-sm" />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-graphite">Payment mode</dt>
                <dd className="mt-2">
                  <ModeMark mode={r.mode} />
                  <span className="ml-2 text-sm text-ink-soft">{r.mode.toUpperCase() === "REAL" ? "Real Lightning" : "Demo invoice, no sats moved"}</span>
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-graphite">Settled</dt>
                <dd className="num mt-1 text-sm font-medium">{stamp(r.settled_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-graphite">Dispute</dt>
                <dd className="mt-1 text-sm font-medium">{r.dispute === "none" ? "None raised" : "Upheld"}</dd>
              </div>
            </dl>

            <dl className="divide-y divide-rule/80">
              <HashField label="Job" value={r.job_id} />
              <HashField label="Payment hash" value={r.payment_hash} hint="The invoice's lock" />
              <HashField label="Preimage" value={r.preimage} hint="Opens the payment hash" />
              <HashField label="Result hash" value={r.result_hash} hint="Committed before payment" />
              <HashField label="Key commitment" value={r.key_commitment} />
              <HashField label="Ciphertext hash" value={r.ciphertext_hash} />
            </dl>

            <div className="mt-6 space-y-3">
              {check ? <Verdict check={check} /> : null}
              <div className="no-print flex flex-wrap items-center gap-3">
                <Button variant="seal" onClick={() => void verify()}>
                  {check ? "Verify again" : "Verify"}
                </Button>
                <Button variant="outline" onClick={() => window.print()}>
                  <Printer aria-hidden /> Print
                </Button>
                <span className="text-xs text-graphite">The check runs in your browser (Web Crypto, SHA-256). Nothing is sent anywhere.</span>
              </div>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-5 border-t border-rule pt-6">
              {qr ? (
                <img src={qr} alt={`QR code linking to this receipt, ${url}`} width={112} height={112} className={cn("size-28 rounded-[4px] border border-rule bg-white")} />
              ) : null}
              <p className="min-w-0 max-w-[46ch] text-xs leading-relaxed text-graphite">
                Scan to open this receipt. The page holds only hashes and amounts: no keys, no tokens and none of the job&rsquo;s content.
                <span className="hash mt-1 block break-all text-2xs">{url}</span>
              </p>
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
