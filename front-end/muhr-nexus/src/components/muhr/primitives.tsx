import { useEffect, useRef, useState } from "react";
import { gsap, prefersReducedMotion } from "@/lib/motion";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { statusLabel, statusTone, type StatusTone } from "@/lib/format";

/** The wax-seal mark used in the wordmark and favicon. */
export function SealMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <circle cx="16" cy="16" r="15" fill="hsl(var(--seal))" />
      <circle cx="16" cy="16" r="11.5" fill="none" stroke="hsl(var(--sheet))" strokeOpacity=".45" strokeWidth="1" />
      <path d="M10 22.5V10l6 7.5L22 10v12.5" stroke="hsl(var(--sheet))" strokeWidth="2.6" strokeLinecap="square" strokeLinejoin="miter" fill="none" />
    </svg>
  );
}

const toneClass: Record<StatusTone, string> = {
  settled: "bg-settled-tint text-settled",
  pending: "bg-pending-tint text-pending",
  broken: "bg-seal-tint text-seal",
  neutral: "bg-secondary text-graphite",
};

const dotClass: Record<StatusTone, string> = {
  settled: "bg-settled",
  pending: "bg-pending",
  broken: "bg-seal",
  neutral: "bg-graphite",
};

export function StatusMark({ status, className }: { status: string; className?: string }) {
  const tone = statusTone(status);
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", toneClass[tone], className)}>
      <span className={cn("size-1.5 rounded-full", dotClass[tone])} aria-hidden />
      {statusLabel(status)}
    </span>
  );
}

export function ModeMark({ mode }: { mode: string | null | undefined }) {
  if (!mode) return null;
  const real = mode.toUpperCase() === "REAL";
  return (
    <span
      title={real ? "Real Lightning payment" : "Demo invoice: no sats move"}
      className={cn(
        "inline-flex items-center rounded-[3px] border px-1.5 text-2xs font-semibold",
        real ? "border-settled/40 text-settled" : "border-rule-strong text-graphite",
      )}
    >
      {real ? "Real sats" : "Demo"}
    </span>
  );
}

const HEX = "0123456789abcdef";

/**
 * A hash that resolves left to right out of random hex, like a value being read off
 * the record. Runs once per value; the final text is always the real value.
 */
export function Decode({ text, delay = 0, className }: { text: string; delay?: number; className?: string }) {
  const el = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    node.textContent = text;
    if (prefersReducedMotion()) return;
    const state = { p: 0 };
    const tween = gsap.to(state, {
      p: 1,
      duration: Math.min(1.1, 0.35 + text.length * 0.008),
      delay,
      ease: "power2.out",
      onUpdate: () => {
        const fixed = Math.floor(state.p * text.length);
        let out = text.slice(0, fixed);
        for (let i = fixed; i < text.length; i++) {
          const c = text[i]!;
          out += /[0-9a-f]/i.test(c) ? HEX[(Math.random() * 16) | 0] : c;
        }
        node.textContent = out;
      },
      onComplete: () => {
        node.textContent = text;
      },
    });
    return () => {
      tween.kill();
      node.textContent = text;
    };
  }, [text, delay]);
  return (
    <span className={className}>
      <span className="sr-only">{text}</span>
      <span ref={el} aria-hidden />
    </span>
  );
}

/** Label + monospace value with a copy button. `decode` resolves the value in when it changes. */
export function HashField({
  label,
  value,
  hint,
  stacked,
  decode,
}: {
  label: string;
  value: string | null | undefined;
  hint?: string;
  stacked?: boolean;
  decode?: number;
}) {
  const [copied, setCopied] = useState(false);
  const has = Boolean(value);
  return (
    <div className={cn("grid gap-1 py-2.5", !stacked && "sm:grid-cols-[10.5rem_1fr] sm:gap-4")}>
      <dt className="text-xs text-graphite">
        {label}
        {hint ? <span className="block text-2xs text-graphite/80">{hint}</span> : null}
      </dt>
      <dd className="flex min-w-0 items-start justify-between gap-2">
        {has && decode != null ? (
          <Decode text={value!} delay={decode} className="hash min-w-0 text-ink" />
        ) : (
          <span className={cn("hash min-w-0", has ? "text-ink" : "text-graphite")}>{has ? value : "Not yet"}</span>
        )}
        {has ? (
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard?.writeText(value!).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1200);
              });
            }}
            className="shrink-0 rounded-[3px] p-1 text-graphite hover:bg-ink/5 hover:text-ink"
            aria-label={`Copy ${label}`}
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          </button>
        ) : null}
      </dd>
    </div>
  );
}

export function SectionHead({ title, children, className }: { title: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1", className)}>
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {children ? <div className="text-xs text-graphite">{children}</div> : null}
    </div>
  );
}

export function EmptyNote({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 py-8 text-sm text-graphite">
      <p className="max-w-[46ch]">{children}</p>
      {action}
    </div>
  );
}
