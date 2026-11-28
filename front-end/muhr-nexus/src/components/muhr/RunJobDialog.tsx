import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { capabilityLabel, sats } from "@/lib/format";
import type { SellerInfo } from "@/types/api";
import { PkrNote } from "./Amount";

export const SAMPLE_TEXT =
  "Lightning payments suit AI agents because the jobs are tiny, frequent and too cheap for cards. A buyer agent seals its data to a specialist seller, the seller commits to a result before it is paid, and the buyer releases payment only against that commitment. Muhr turns this into a marketplace where agents find capabilities, post tasks and settle work without escrow.";

type Direction = "ur_to_en" | "en_to_ur";
const DIRECTIONS: Array<{ id: Direction; label: string }> = [
  { id: "ur_to_en", label: "Urdu → English" },
  { id: "en_to_ur", label: "English → Urdu" },
];
/** Urdu script means Urdu to English; anything else is taken to be English. */
const guessDirection = (s: string): Direction => (/[\u0600-\u06FF]/.test(s) ? "ur_to_en" : "en_to_ur");

export function RunJobDialog({
  open,
  onOpenChange,
  sellers,
  busy,
  onRun,
  sellerReachable,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  sellers: SellerInfo[] | undefined;
  busy: boolean;
  onRun: (args: { text: string; sellerId: string; budget: number }) => void;
  sellerReachable: boolean | null;
}) {
  const active = (sellers ?? []).filter((s) => s.status === "active");
  const [text, setText] = useState(SAMPLE_TEXT);
  const [sellerId, setSellerId] = useState("sel_summarizer");
  const [budget, setBudget] = useState(100);
  const [picked, setPicked] = useState<Direction | null>(null);

  useEffect(() => {
    if (active.length && !active.some((s) => s.seller_id === sellerId)) setSellerId(active[0]!.seller_id);
  }, [active, sellerId]);

  // The page behind runs smooth scrolling that would otherwise eat the wheel: pause it while the dialog is open.
  useEffect(() => {
    if (!open) return;
    const l = (window as unknown as { __lenis?: { stop: () => void; start: () => void } }).__lenis;
    l?.stop();
    return () => l?.start();
  }, [open]);

  const chosen = active.find((s) => s.seller_id === sellerId);
  const isUrdu = chosen?.capability === "urdu_translation";
  const direction = picked ?? guessDirection(text);

  return (
    <Dialog open={open} onOpenChange={(v) => !busy && onOpenChange(v)}>
      <DialogContent data-lenis-prevent className="flex max-h-[92dvh] max-w-2xl flex-col gap-4">
        <DialogHeader>
          <DialogTitle className="type-wide text-2xl font-bold">Run a job</DialogTitle>
          <DialogDescription>
            The registry acts as a buyer and runs the full flow: post, quote, seal, commit, invoice, pay, settle. It uses demo invoices, so no sats
            move. Watch each step land on the line.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1" data-lenis-prevent>
        <fieldset>
          <legend className="mb-2 text-sm font-semibold">Seller</legend>
          {active.length === 0 ? (
            <p className="text-sm text-seal">No sellers are online. Start them with start_sellers.bat, then try again.</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {active.map((s) => {
                const on = s.seller_id === sellerId;
                return (
                  <label
                    key={s.seller_id}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-[4px] border p-3 transition-colors",
                      on ? "border-ink bg-ink/[0.03]" : "border-rule-strong hover:border-ink/60",
                    )}
                  >
                    <input
                      type="radio"
                      name="seller"
                      value={s.seller_id}
                      checked={on}
                      onChange={() => setSellerId(s.seller_id)}
                      className="mt-1 accent-[hsl(var(--ink))]"
                    />
                    <span>
                      <span className="block text-sm font-semibold">{capabilityLabel(s.capability)}</span>
                      <span className="num block text-xs text-graphite">
                        {sats(s.price_sats_per_unit)} sats {s.unit_definition} <PkrNote sats={s.price_sats_per_unit} />
                      </span>
                      <span className="hash block text-2xs text-graphite/80">{s.seller_id}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        </fieldset>

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <label htmlFor="job-input" className="text-sm font-semibold">
              Input
            </label>
            <button type="button" className="text-xs text-graphite underline-offset-4 hover:text-ink hover:underline" onClick={() => setText(SAMPLE_TEXT)} disabled={busy}>
              Use sample text
            </button>
          </div>
          <textarea
            id="job-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            className="w-full resize-y rounded-[4px] border border-rule-strong bg-paper/60 p-3 text-sm leading-relaxed outline-none focus:border-ink"
          />
          <p className="mt-1 text-2xs text-graphite">Sealed to the seller&rsquo;s key before it leaves. The registry only sees its size.</p>
        </div>

        {isUrdu ? (
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">Translate</legend>
            <div className="flex flex-wrap gap-2">
              {DIRECTIONS.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  aria-pressed={direction === d.id}
                  onClick={() => setPicked(d.id)}
                  disabled={busy}
                  className={cn(
                    "rounded-[4px] border px-3 py-2 text-sm font-semibold transition-colors",
                    direction === d.id ? "border-ink bg-ink/[0.03]" : "border-rule-strong text-graphite hover:border-ink/60",
                  )}
                >
                  {d.label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-2xs text-graphite">
              {picked ? "You chose this direction." : "Picked from your text: Urdu script is translated to English, anything else to Urdu."}
            </p>
          </fieldset>
        ) : null}

        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label htmlFor="job-budget" className="mb-2 block text-sm font-semibold">
              Budget
            </label>
            <div className="flex items-center rounded-[4px] border border-rule-strong bg-paper/60 focus-within:border-ink">
              <input
                id="job-budget"
                type="number"
                min={1}
                max={10000}
                value={budget}
                onChange={(e) => setBudget(Math.max(1, Math.min(10000, Number(e.target.value) || 1)))}
                className="num h-10 w-28 bg-transparent px-3 text-sm outline-none"
              />
              <span className="pr-3 text-xs text-graphite">sats</span>
            </div>
          </div>
          <p className="pb-2.5 text-xs text-graphite">
            <PkrNote sats={budget} /> at this budget
          </p>
          {chosen ? <p className="pb-2.5 text-xs text-graphite">The seller quotes a price up to this budget. You&rsquo;re charged the quote.</p> : null}
        </div>

        {sellerReachable === false ? (
          <p className="rounded-[4px] bg-pending-tint px-3 py-2 text-xs text-pending">
            The registry can&rsquo;t reach the summarizer right now, so this may fail. Check that the sellers are running.
          </p>
        ) : null}
        </div>

        <DialogFooter className="shrink-0 gap-2 sm:gap-2">
          <Button variant="ghost" type="button" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="seal"
            type="button"
            disabled={busy || !text.trim() || !chosen}
            onClick={() =>
              onRun({ text: isUrdu ? JSON.stringify({ text: text.trim(), direction }) : text.trim(), sellerId, budget })
            }
          >
            {busy ? "Running the job…" : "Run job"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
