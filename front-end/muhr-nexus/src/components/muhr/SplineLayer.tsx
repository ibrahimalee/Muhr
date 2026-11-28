import { useEffect, useRef } from "react";
import { ScrollTrigger } from "@/lib/motion";

export const SPLINE_SCENE = ((import.meta.env.VITE_SPLINE_SCENE as string | undefined) ?? "").trim();

/**
 * Optional Spline scene (VITE_SPLINE_SCENE, a .splinecode URL) rendered behind the
 * envelope. The runtime is downloaded only when a scene is configured. The story's
 * scroll timeline turns this layer along with the envelope.
 */
export function SplineLayer() {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!SPLINE_SCENE) return;
    let app: { dispose?: () => void } | null = null;
    let cancelled = false;
    void import("@splinetool/runtime").then(async ({ Application }) => {
      if (cancelled || !canvas.current) return;
      const a = new Application(canvas.current);
      app = a as unknown as { dispose?: () => void };
      await a.load(SPLINE_SCENE);
      if (!cancelled) ScrollTrigger.refresh();
    });
    return () => {
      cancelled = true;
      app?.dispose?.();
    };
  }, []);
  if (!SPLINE_SCENE) return null;
  return (
    <div data-spline className="pointer-events-none absolute -inset-[12%] [transform:translateZ(-80px)]" aria-hidden>
      <canvas ref={canvas} className="h-full w-full" />
    </div>
  );
}
