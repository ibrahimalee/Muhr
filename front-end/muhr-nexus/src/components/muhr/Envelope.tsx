import { cn } from "@/lib/utils";
import { sats, shortHash } from "@/lib/format";
import { WaxSeal } from "./WaxSeal";
import { Amount } from "./Amount";

/*
 * The protocol, as one object. Coordinates live in a 600 x 540 box so the SVG overlay
 * (coin arc) and the HTML layers line up exactly at any size.
 *
 * Layers, back to front: body, input sheet, result slip, front pocket, flap, seal,
 * hash tags, invoice, coin.
 */
export const SCENE_W = 600;
export const SCENE_H = 540;
export const COIN_ARC = "M 236 392 C 250 300, 300 210, 318 276";

export type SceneData = {
  amount: number | null;
  resultHash: string | null;
  keyCommitment: string | null;
  ciphertextHash: string | null;
  paymentHash: string | null;
  capability: string | null;
};

const pct = (n: number, of: number) => `${(n / of) * 100}%`;

function Tag({ label, value, idx }: { label: string; value: string | null; idx: number }) {
  return (
    <div
      data-tag
      className="glass absolute flex items-center gap-3 !rounded-[8px] px-3.5 py-2.5"
      style={{ left: pct(384, SCENE_W), top: pct(112 + idx * 66, SCENE_H), width: pct(214, SCENE_W) }}
    >
      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-ink text-[10px] font-bold text-sheet shadow-[inset_0_1px_0_hsl(0_0%_100%/.3)]">
        {idx + 1}
      </span>
      <span className="min-w-0">
        <span className="block text-2xs text-graphite">{label}</span>
        <span className="hash block truncate text-xs text-ink">{value ? shortHash(value, 8, 6) : "sha256 on record"}</span>
      </span>
    </div>
  );
}

export function Envelope({ data, sealed = false, className }: { data: SceneData; sealed?: boolean; className?: string }) {
  return (
    <div className={cn("relative w-full [transform-style:preserve-3d]", className)} style={{ aspectRatio: `${SCENE_W} / ${SCENE_H}` }}>
      {/* floor shadow */}
      <div
        data-shadow
        className="absolute rounded-[50%] bg-ink/25 blur-2xl"
        style={{ left: pct(150, SCENE_W), width: pct(340, SCENE_W), top: pct(400, SCENE_H), height: pct(44, SCENE_H) }}
      />

      <div
        data-env
        className="absolute [transform-style:preserve-3d]"
        style={{ left: pct(132, SCENE_W), width: pct(372, SCENE_W), top: pct(162, SCENE_H), height: pct(216, SCENE_H) }}
      >
        {/* back of the envelope */}
        <div
          className="absolute inset-0 rounded-[10px]"
          style={{
            background: "linear-gradient(170deg, hsl(85 12% 90%), hsl(90 9% 82%))",
            boxShadow: "0 40px 60px -36px hsl(var(--ink) / 0.6), inset 0 1px 0 hsl(0 0% 100% / 0.7)",
          }}
        />

        {/* input sheet: drops in during "Sealed" */}
        <div data-sheet className={cn("absolute rounded-[6px] border border-rule bg-sheet p-3 shadow-[0_14px_30px_-18px_hsl(var(--ink)/0.6)]", sealed && "hidden")} style={{ left: "9%", right: "9%", top: "4%", height: "88%", transform: "translateZ(3px)" }}>
          <div className="flex items-center justify-between text-2xs text-graphite">
            <span>Your input</span>
            <span className="hash">{data.capability ? data.capability.replace(/_/g, " ") : "plain text"}</span>
          </div>
          <div className="mt-2.5 space-y-1.5" aria-hidden>
            {[94, 82, 88, 70, 90, 62].map((w, i) => (
              <div key={i} className="h-1.5 rounded bg-ink/25" style={{ width: `${w}%` }} />
            ))}
          </div>
        </div>

        {/* result slip: rises during "Opened" */}
        <div data-slip className={cn("absolute rounded-[6px] border border-rule bg-sheet p-3 shadow-[0_14px_30px_-18px_hsl(var(--ink)/0.6)]", sealed && "hidden")} style={{ left: "7%", right: "7%", top: "6%", height: "86%", transform: "translateZ(3px)" }}>
          <div className="flex items-center justify-between text-2xs">
            <span className="font-semibold text-ink">Result, decrypted</span>
            <span className="font-semibold text-settled">Hash matches</span>
          </div>
          <div className="mt-2.5 space-y-1.5" aria-hidden>
            {[92, 86, 74, 88].map((w, i) => (
              <div key={i} className="h-1.5 rounded bg-ink/70" style={{ width: `${w}%`, opacity: i ? 0.55 : 1 }} />
            ))}
          </div>
          <div className="mt-3 text-sm font-semibold">
            {data.amount != null ? (
              <>
                <span className="font-normal text-graphite">Paid </span>
                <Amount sats={data.amount} inline />
              </>
            ) : (
              "Paid on delivery"
            )}
          </div>
        </div>

        {/* front pocket: bottom and side folds */}
        <svg viewBox="0 0 100 64" preserveAspectRatio="none" className="absolute inset-0 h-full w-full [transform:translateZ(6px)]" aria-hidden>
          <defs>
            <linearGradient id="pocket" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="hsl(85 14% 95%)" />
              <stop offset="1" stopColor="hsl(90 9% 86%)" />
            </linearGradient>
          </defs>
          <path d="M0 2 L46 36 L0 64 Z" fill="hsl(85 12% 92%)" />
          <path d="M100 2 L54 36 L100 64 Z" fill="hsl(85 12% 91%)" />
          <path d="M0 64 L50 29 L100 64 Z" fill="url(#pocket)" />
          <path d="M0 64 L50 29 L100 64" fill="none" stroke="hsl(var(--rule-strong) / .6)" strokeWidth=".35" vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="pointer-events-none absolute inset-0 rounded-[10px] border border-white/70 [transform:translateZ(6.5px)]" />

        {/* flap, hinged on the top edge */}
        <div
          data-flap
          className="absolute inset-x-0 top-0 h-[58%] origin-top [transform-style:preserve-3d]"
          style={{ transform: sealed ? "translateZ(7px)" : "translateZ(1px) rotateX(184deg)" }}
        >
          <svg viewBox="0 0 100 58" preserveAspectRatio="none" className="absolute inset-0 h-full w-full [backface-visibility:hidden]" aria-hidden>
            <path d="M0 0 H100 L54 54 Q50 58 46 54 Z" fill="hsl(85 16% 95%)" stroke="hsl(var(--rule-strong) / .8)" strokeWidth=".4" vectorEffect="non-scaling-stroke" />
          </svg>
          <svg viewBox="0 0 100 58" preserveAspectRatio="none" className="absolute inset-0 h-full w-full [backface-visibility:hidden] [transform:rotateY(180deg)]" aria-hidden>
            <path d="M0 0 H100 L54 54 Q50 58 46 54 Z" fill="hsl(90 8% 80%)" />
          </svg>
        </div>
      </div>

      {/* wax seal on the flap tip */}
      <div
        data-seal
        className="absolute [transform-style:preserve-3d]"
        style={{ left: pct(318 - 58, SCENE_W), top: pct(276 - 58, SCENE_H), width: pct(116, SCENE_W), opacity: sealed ? 1 : 0, transform: "translateZ(30px)" }}
      >
        <div className="drop-shadow-[0_12px_14px_hsl(5_70%_18%/0.45)]">
          <WaxSeal className="w-full" legendRef={undefined} />
        </div>
      </div>

      {/* committed hashes */}
      <div data-tags className="absolute inset-0 [transform-style:preserve-3d] [transform:translateZ(140px)]" style={{ opacity: 0 }}>
        <Tag idx={0} label="Result hash" value={data.resultHash} />
        <Tag idx={1} label="Key commitment" value={data.keyCommitment} />
        <Tag idx={2} label="Ciphertext hash" value={data.ciphertextHash} />
      </div>

      {/* invoice */}
      <div
        data-invoice
        className="glass absolute !rounded-[10px] p-4"
        style={{ left: pct(14, SCENE_W), top: pct(352, SCENE_H), width: pct(236, SCENE_W), opacity: 0, transform: "translateZ(150px)" }}
      >
        <div className="flex items-center justify-between text-2xs text-graphite">
          <span>Lightning invoice</span>
          <span>Checked</span>
        </div>
        <div className="num mt-1.5 text-xl font-semibold leading-none">
          {data.amount != null ? <Amount sats={data.amount} inline pkrClassName="text-xs font-normal" /> : "–"}
        </div>
        <div className="hash mt-2 truncate text-2xs text-graphite">{data.paymentHash ? shortHash(data.paymentHash, 10, 8) : "lnbc…"}</div>
        <div
          data-paid
          className="absolute -right-3 -top-3 rotate-[-10deg] rounded-[6px] border-2 border-settled bg-settled-tint px-2 py-0.5 text-xs font-extrabold text-settled shadow-[0_6px_12px_-6px_hsl(var(--settled)/.7)]"
          style={{ opacity: 0 }}
        >
          Paid
        </div>
      </div>

      {/* coin path */}
      <svg viewBox={`0 0 ${SCENE_W} ${SCENE_H}`} className="pointer-events-none absolute inset-0 h-full w-full overflow-visible [transform:translateZ(160px)]" aria-hidden>
        <path data-arc d={COIN_ARC} fill="none" stroke="hsl(40 62% 45%)" strokeWidth="1.6" strokeDasharray="3 6" strokeLinecap="round" style={{ opacity: 0 }} />
        <g data-coin style={{ opacity: 0 }}>
          <circle r="15" fill="url(#coinClay)" stroke="hsl(36 60% 30% / .5)" />
          <circle r="10.5" fill="none" stroke="hsl(0 0% 100% / .45)" />
          <path d="M1.6 -8 L-4.8 1.4 H-0.3 L-1.6 8 L4.8 -1.4 H0.3 Z" fill="hsl(36 70% 22%)" />
        </g>
        <defs>
          <radialGradient id="coinClay" cx="35%" cy="30%" r="75%">
            <stop offset="0%" stopColor="hsl(42 70% 72%)" />
            <stop offset="60%" stopColor="hsl(40 62% 48%)" />
            <stop offset="100%" stopColor="hsl(36 70% 30%)" />
          </radialGradient>
        </defs>
      </svg>
    </div>
  );
}
