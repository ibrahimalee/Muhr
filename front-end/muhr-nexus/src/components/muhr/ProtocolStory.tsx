import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { gsap, prefersReducedMotion, scrollToEl, useGSAP } from "@/lib/motion";
import { COIN_ARC, Envelope, type SceneData } from "./Envelope";
import { SplineLayer } from "./SplineLayer";

const ACTS = [
  {
    n: "01",
    name: "Sealed",
    title: "Your data is sealed to one seller.",
    body: "The buyer agent encrypts its input to the seller’s public key before it leaves. The registry in the middle only ever sees its size.",
  },
  {
    n: "02",
    name: "Committed",
    title: "The seller commits before it’s paid.",
    body: "It runs the job, locks the result, and publishes three hashes: the result, its key, and the ciphertext. None of them can change later.",
  },
  {
    n: "03",
    name: "Paid",
    title: "The invoice is checked, then paid.",
    body: "The buyer matches the Lightning invoice against the registry record, same hash and same price, before a single sat moves.",
  },
  {
    n: "04",
    name: "Opened",
    title: "Paying is what opens it.",
    body: "Payment releases the result key. The buyer decrypts, checks the hash, and the job settles. A result that doesn’t match costs the seller half its stake.",
  },
] as const;

const HEADLINE = "Sell your AI tool to the world. Get paid in seconds. No PayPal needed.";

function Words({ text, className }: { text: string; className?: string }) {
  return (
    <span className={className} aria-label={text}>
      {text.split(" ").map((w, i) => [
        i ? " " : null,
        <span key={i} aria-hidden className="inline-block overflow-hidden pb-[0.1em] align-bottom">
          <span data-w className="inline-block will-change-transform">
            {w}
          </span>
        </span>,
      ])}
    </span>
  );
}

/** True when the pinned, scroll-driven version should run. */
function useCinematic() {
  const q = "(min-width: 768px) and (min-height: 520px) and (prefers-reduced-motion: no-preference)";
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const f = () => setOn(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);
  return on;
}

function Hero({ onRun, cinematic }: { onRun: () => void; cinematic: boolean }) {
  return (
    <div data-hero>
      <h1 className="type-wide max-w-[19ch] text-[2.1rem] font-extrabold leading-[1] tracking-[-0.02em] sm:text-[2.8rem] md:text-[2.1rem] lg:text-[3.1rem] xl:text-[3.5rem]">
        <Words text={HEADLINE} />
      </h1>
      <div data-hero-rest>
      <p data-hero-sub className="mt-7 max-w-[44ch] text-[1.0625rem] leading-relaxed text-ink-soft">
        Muhr pays sellers per job over Lightning. The buyer&rsquo;s data stays sealed, and the result unlocks only when payment arrives.
      </p>
      <div data-hero-sub className="mt-9 flex flex-wrap items-center gap-3">
        <Button variant="seal" size="lg" className="muhr-arrow" onClick={onRun}>
          Run a job <ArrowRight />
        </Button>
        {cinematic ? (
          <span className="ml-2 inline-flex items-center gap-3 text-sm text-graphite">
            <span className="muhr-scroll-cue" aria-hidden />
            Scroll to follow a job
          </span>
        ) : (
          <Button
            variant="ghost"
            size="lg"
            className="muhr-arrow-down"
            onClick={() => scrollToEl(document.getElementById("acts"))}
          >
            How it works <ArrowDown />
          </Button>
        )}
      </div>
      </div>
    </div>
  );
}

/** A vertical SVG rail with one stop per act; it draws itself with the story. */
function Rail() {
  return (
    <svg data-rail-svg viewBox="0 0 24 300" className="h-[300px] w-6 overflow-visible" aria-hidden>
      <path d="M12 6 V294" stroke="hsl(var(--rule-strong))" strokeWidth="1.5" strokeDasharray="2 5" strokeLinecap="round" fill="none" />
      <path data-rail d="M12 6 V294" stroke="hsl(var(--ink))" strokeWidth="2.5" strokeLinecap="round" fill="none" pathLength={1} strokeDasharray="1" strokeDashoffset="1" />
      {ACTS.map((_, i) => (
        <circle key={i} data-node cx="12" cy={6 + i * 96} r="6" fill="hsl(var(--paper))" stroke="hsl(var(--rule-strong))" strokeWidth="2" />
      ))}
    </svg>
  );
}

export function ProtocolStory({ data, onRun }: { data: SceneData; onRun: () => void }) {
  const cinematic = useCinematic();
  const root = useRef<HTMLElement>(null);
  const tilt = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const el = root.current;
      if (!el) return;
      const q = gsap.utils.selector(el);
      const words = q("[data-hero] [data-w]");

      if (prefersReducedMotion()) return;

      // Arrival: headline words rise, then the supporting copy.
      gsap.from(words, { yPercent: 110, rotate: 5, duration: 1.1, ease: "power4.out", stagger: 0.06, delay: 0.1 });
      gsap.from(q("[data-hero-sub]"), { y: 18, autoAlpha: 0, duration: 0.9, ease: "power3.out", stagger: 0.12, delay: 0.55 });

      if (!cinematic) {
        // Static layout: each act reveals as it scrolls in.
        q("[data-act-card]").forEach((card) =>
          gsap.from(card, { y: 40, autoAlpha: 0, duration: 0.9, ease: "power3.out", scrollTrigger: { trigger: card, start: "top 85%" } }),
        );
        gsap.from(q("[data-scene]"), { y: 40, rotateX: 18, autoAlpha: 0, duration: 1.2, ease: "power3.out", delay: 0.3 });
        return;
      }

      const env = q("[data-env]");
      const sheet = q("[data-sheet]");
      const slip = q("[data-slip]");
      const flap = q("[data-flap]");
      const seal = q("[data-seal]");
      const tags = q("[data-tag]");
      const invoice = q("[data-invoice]");
      const paid = q("[data-paid]");
      const coin = q("[data-coin]")[0] as unknown as SVGGElement | undefined;
      const arc = q("[data-arc]")[0] as unknown as SVGPathElement | undefined;
      const acts = q("[data-act]");
      const nodes = q("[data-node]");

      // Starting pose: envelope open, input hovering above it.
      // Depths: back 0, open flap 1px, papers 3px, pocket 6px, closed flap 7px, seal 30px, tags 140px, invoice 150px, coin 160px.
      gsap.set(flap, { z: 1, rotateX: 184 }); // open: behind the paper
      gsap.set([sheet, slip], { z: 3 });
      gsap.set(sheet, { yPercent: -92 });
      gsap.set(slip, { yPercent: 0, autoAlpha: 0 });
      gsap.set(seal, { z: 30, scale: 2.2, autoAlpha: 0, rotate: -25 });
      gsap.set(invoice, { z: 150 });
      gsap.set(q("[data-tags]"), { autoAlpha: 1 });
      gsap.set(tags, { x: -120, autoAlpha: 0 });
      gsap.set(invoice, { y: 90, rotateX: 25, autoAlpha: 0 });
      gsap.set(acts, { autoAlpha: 0 });
      gsap.set(q("[data-act] [data-w]"), { yPercent: 110 });
      gsap.set(q("[data-act] [data-act-body]"), { y: 16, autoAlpha: 0 });
      gsap.set(q("[data-rail-wrap]"), { autoAlpha: 0, x: -10 });

      // Scene entrance.
      gsap.from(q("[data-scene]"), { y: 60, rotateX: 22, autoAlpha: 0, duration: 1.4, ease: "power3.out", delay: 0.2 });

      const coinPos = { t: 0 };
      const arcLen = arc?.getTotalLength() ?? 0;
      const placeCoin = () => {
        if (!arc || !coin) return;
        const p = arc.getPointAtLength(arcLen * coinPos.t);
        coin.setAttribute("transform", `translate(${p.x} ${p.y})`);
      };
      placeCoin();

      const showAct = (tl: gsap.core.Timeline, i: number, at: number) => {
        const a = acts[i];
        tl.set(a, { autoAlpha: 1 }, at)
          .to(a.querySelectorAll("[data-w]"), { yPercent: 0, stagger: 0.04, duration: 0.5, ease: "power3.out" }, at)
          .to(a.querySelector("[data-act-body]"), { y: 0, autoAlpha: 1, duration: 0.5, ease: "power3.out" }, at + 0.2)
          .to(nodes[i], { attr: { r: 7 }, fill: "#172034", stroke: "#172034", duration: 0.3 }, at);
      };
      const hideAct = (tl: gsap.core.Timeline, i: number, at: number) => {
        const a = acts[i];
        tl.to(a.querySelectorAll("[data-w]"), { yPercent: -110, stagger: 0.02, duration: 0.4, ease: "power2.in" }, at)
          .to(a.querySelector("[data-act-body]"), { y: -12, autoAlpha: 0, duration: 0.35, ease: "power2.in" }, at)
          .set(a, { autoAlpha: 0 }, at + 0.5);
      };

      const tl = gsap.timeline({
        defaults: { ease: "power2.inOut" },
        scrollTrigger: { trigger: el, start: "top top", end: () => `+=${window.innerHeight * 5}`, pin: q("[data-pin]")[0], scrub: 1, anticipatePin: 1 },
      });

      // 0 – 1: the hero steps aside.
      // The intro animates yPercent/opacity; the exit uses y and a wrapper, so the two never fight
      // (e.g. when the page is reloaded halfway down and the intro plays mid-story).
      tl.to(words, { y: -140, stagger: 0.015, duration: 0.6, ease: "power2.in" }, 0)
        .to(q("[data-hero-rest]"), { y: -24, autoAlpha: 0, duration: 0.5, ease: "power2.in" }, 0.1)
        .to(q("[data-rail-wrap]"), { autoAlpha: 1, x: 0, duration: 0.5 }, 0.6)
        .to(q("[data-rail]"), { strokeDashoffset: 0, ease: "none", duration: 9 }, 1);

      // 1 – 3: Sealed.
      showAct(tl, 0, 1);
      tl.to(sheet, { yPercent: 0, duration: 0.9, ease: "power2.inOut" }, 1.1)
        .to(flap, { rotateX: 0, z: 7, duration: 0.8, ease: "power2.inOut" }, 1.9)
        .to(seal, { scale: 1, autoAlpha: 1, rotate: 0, duration: 0.45, ease: "back.out(2.4)" }, 2.55)
        .to(env, { y: 6, duration: 0.12, yoyo: true, repeat: 1, ease: "power1.inOut" }, 2.6);
      hideAct(tl, 0, 3.1);

      // 3 – 5.3: Committed.
      showAct(tl, 1, 3.4);
      tl.to(env, { rotateY: -24, rotateX: 6, x: -30, duration: 0.9 }, 3.3)
        .to(seal, { rotateY: -24, x: -30, duration: 0.9 }, 3.3)
        .to(tags, { x: 0, autoAlpha: 1, stagger: 0.18, duration: 0.6, ease: "power3.out" }, 3.6);
      hideAct(tl, 1, 5.3);

      // 5.3 – 7.6: Paid.
      showAct(tl, 2, 5.6);
      tl.to(tags, { x: 60, autoAlpha: 0, stagger: 0.08, duration: 0.5, ease: "power2.in" }, 5.4)
        .set(tags, { display: "none" }, 6.2) // out of the layout once faded, so they never add a sideways scrollbar
        .to([env, seal], { rotateY: -6, rotateX: 2, x: 0, duration: 0.8 }, 5.5)
        .to(invoice, { y: 0, rotateX: 0, autoAlpha: 1, duration: 0.7, ease: "power3.out" }, 5.7)
        .to(arc ?? {}, { opacity: 1, duration: 0.3 }, 6.3)
        .set(coin ?? {}, { opacity: 1 }, 6.4)
        .to(coinPos, { t: 1, duration: 0.9, ease: "power2.inOut", onUpdate: placeCoin }, 6.4)
        .to(paid, { autoAlpha: 1, scale: 1, startAt: { scale: 2.4 }, duration: 0.35, ease: "back.out(2)" }, 6.5)
        .to(coin ?? {}, { opacity: 0, duration: 0.15 }, 7.25)
        .to(arc ?? {}, { opacity: 0, duration: 0.3 }, 7.25)
        .to(seal, { scale: 1.12, duration: 0.15, yoyo: true, repeat: 1 }, 7.25);
      hideAct(tl, 2, 7.6);

      // 7.6 – 10: Opened.
      showAct(tl, 3, 7.9);
      tl.to(invoice, { y: 40, autoAlpha: 0, duration: 0.5, ease: "power2.in" }, 7.7)
        .to(seal, { y: -170, x: 110, rotate: 200, rotateY: 60, scale: 0.6, autoAlpha: 0, duration: 1, ease: "power2.in" }, 7.9)
        .to(flap, { rotateX: 184, z: 1, duration: 0.9 }, 8.2)
        .set(sheet, { autoAlpha: 0 }, 8.2)
        .set(slip, { autoAlpha: 1 }, 8.2)
        .to(slip, { yPercent: -78, duration: 1, ease: "power3.out" }, 8.6)
        .to(env, { rotateY: 8, rotateX: -4, duration: 1.2 }, 8.4)
        .to({}, { duration: 0.6 }, 9.6);
      // An optional Spline scene behind the envelope turns through the whole story.
      if (q("[data-spline]").length) tl.fromTo(q("[data-spline]"), { rotateY: -20 }, { rotateY: 40, rotateX: -8, ease: "none", duration: 10 }, 0);
    },
    { scope: root, dependencies: [cinematic], revertOnUpdate: true },
  );

  // Pointer parallax on the scene (desktop only): a few degrees, smoothed.
  useEffect(() => {
    const el = tilt.current;
    if (!el || prefersReducedMotion() || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const rx = gsap.quickTo(el, "rotateX", { duration: 1, ease: "power3.out" });
    const ry = gsap.quickTo(el, "rotateY", { duration: 1, ease: "power3.out" });
    const move = (e: PointerEvent) => {
      ry((e.clientX / window.innerWidth - 0.5) * 10);
      rx(-(e.clientY / window.innerHeight - 0.5) * 7);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, [cinematic]);

  const scene = (
    <div data-scene className="[perspective:1400px]">
      <div ref={tilt} className="relative [transform-style:preserve-3d]">
        <SplineLayer />
        <Envelope data={data} sealed={!cinematic} />
      </div>
    </div>
  );

  if (!cinematic) {
    return (
      <section ref={root} className="relative pt-6">
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <Hero onRun={onRun} cinematic={false} />
          <div className="mx-auto w-full max-w-[520px]">{scene}</div>
        </div>
        <ol id="acts" className="mt-16 grid gap-4 sm:grid-cols-2">
          {ACTS.map((a) => (
            <li key={a.n} data-act-card className="glass p-6">
              <div className="flex items-baseline gap-3">
                <span className="num text-sm font-semibold text-seal">{a.n}</span>
                <span className="text-sm font-semibold">{a.name}</span>
              </div>
              <h3 className="type-wide mt-3 text-xl font-bold leading-tight">{a.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{a.body}</p>
            </li>
          ))}
        </ol>
      </section>
    );
  }

  return (
    <section ref={root} className="relative -mt-6" aria-label="How a job works">
      <div data-pin className="relative flex h-[100svh] items-center">
        <div className="grid w-full items-center gap-6 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:gap-10">
          <div className="relative min-h-[360px] lg:min-h-[420px]">
            <div className="absolute inset-0 flex items-center">
              <Hero onRun={onRun} cinematic />
            </div>
            {/* Acts, stacked in place; the timeline swaps them. */}
            <div data-rail-wrap className="absolute inset-y-0 left-0 flex items-center">
              <Rail />
            </div>
            {ACTS.map((a, i) => (
              <div key={a.n} data-act className="absolute inset-0 flex items-center pl-14">
                <div>
                  <div className="flex items-baseline gap-3 text-sm">
                    <span className="num font-semibold text-seal">{a.n}</span>
                    <span className="font-semibold">{a.name}</span>
                    <span className="text-graphite">of four</span>
                  </div>
                  <h2 className="type-wide mt-4 max-w-[16ch] text-[1.7rem] font-extrabold leading-[1.02] tracking-[-0.015em] lg:text-[2.4rem] xl:text-[2.9rem]">
                    <Words text={a.title} />
                  </h2>
                  <p data-act-body className={cn("mt-5 max-w-[44ch] text-[1.0625rem] leading-relaxed text-ink-soft")}>
                    {a.body}
                  </p>
                  <span className="sr-only">Step {i + 1} of 4</span>
                </div>
              </div>
            ))}
          </div>
          <div className="mx-auto w-full max-w-[640px]">{scene}</div>
        </div>
      </div>
    </section>
  );
}

export { COIN_ARC };
