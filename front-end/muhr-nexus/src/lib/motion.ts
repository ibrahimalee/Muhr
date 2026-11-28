import { useEffect, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Flip } from "gsap/Flip";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, Flip, useGSAP);
// When frames drop (slow device, background tab), finish on time instead of slowing down,
// so content behind an entrance animation is never held back.
gsap.ticker.lagSmoothing(0);

/**
 * Motion rules for Muhr. Every effect on the page follows the job's journey:
 *   - scroll moves the sealed envelope (3D) and draws the dispatch route (SVG),
 *   - things you press are clay (they squash), things that float are glass,
 *   - type moves once, on arrival; nothing loops except the seal's legend.
 * One easing family keeps it coherent.
 */
export const EASE = {
  out: "power3.out",
  inOut: "power2.inOut",
  spring: "back.out(1.6)",
} as const;

export const DUR = { quick: 0.25, base: 0.6, slow: 1.1 } as const;

function query(q: string) {
  return typeof window !== "undefined" && window.matchMedia ? window.matchMedia(q) : null;
}

export function prefersReducedMotion(): boolean {
  return Boolean(query("(prefers-reduced-motion: reduce)")?.matches);
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  useEffect(() => {
    const mq = query("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** True on a mouse or trackpad; false on touch screens, where cursor effects are skipped. */
export function useFinePointer(): boolean {
  const [fine, setFine] = useState(() => Boolean(query("(hover: hover) and (pointer: fine)")?.matches));
  useEffect(() => {
    const mq = query("(hover: hover) and (pointer: fine)");
    if (!mq) return;
    const on = () => setFine(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return fine;
}

export { gsap, Flip, ScrollTrigger, useGSAP };

/**
 * Smooth scrolling (Lenis) driven by GSAP's ticker, so scroll-linked timelines and the
 * scroll position always agree. Off with reduced motion and on touch devices, where
 * native scrolling already feels right.
 */
export function useSmoothScroll() {
  useEffect(() => {
    if (prefersReducedMotion() || !query("(hover: hover) and (pointer: fine)")?.matches) return;
    let lenis: import("lenis").default | null = null;
    let tick: ((t: number) => void) | null = null;
    let cancelled = false;
    void import("lenis").then(({ default: Lenis }) => {
      if (cancelled) return;
      lenis = new Lenis({ lerp: 0.11, wheelMultiplier: 0.95 });
      lenis.on("scroll", ScrollTrigger.update);
      tick = (t: number) => lenis?.raf(t * 1000);
      gsap.ticker.add(tick);
      (window as unknown as { __lenis?: unknown }).__lenis = lenis;
    });
    return () => {
      cancelled = true;
      if (tick) gsap.ticker.remove(tick);
      lenis?.destroy();
    };
  }, []);
}

/** Scroll to an element (smoothly when Lenis is running). */
export function scrollToEl(el: Element | null, offset = -80) {
  if (!el) return;
  const l = (window as unknown as { __lenis?: { scrollTo: (t: Element, o: { offset: number; duration: number }) => void } }).__lenis;
  if (l) l.scrollTo(el, { offset, duration: 1.4 });
  else el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
}

export function scrollToTop() {
  const l = (window as unknown as { __lenis?: { scrollTo: (t: number, o: { immediate: boolean }) => void } }).__lenis;
  if (l) l.scrollTo(0, { immediate: true });
  else window.scrollTo({ top: 0 });
}
