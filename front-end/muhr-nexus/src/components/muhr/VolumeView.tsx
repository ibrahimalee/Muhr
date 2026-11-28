import { useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { sats } from "@/lib/format";
import type { MarketStats } from "@/types/api";
import { EmptyNote, SectionHead } from "./primitives";
import { BentoGrid, Tile } from "./Bento";
import { MoneyFlow } from "./MoneyFlow";
import { prefersReducedMotion } from "@/lib/motion";
import { PkrNote } from "./Amount";

/** Mounts its chart only once it scrolls into view, so the bars rise when they're seen. */
function WhenSeen({ className, children }: { className?: string; children: (animate: boolean) => React.ReactNode }) {
  const el = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e?.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -12% 0px" },
    );
    io.observe(node);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={el} className={className}>
      {seen ? children(!prefersReducedMotion()) : null}
    </div>
  );
}

// Validated pair (dataviz validator, light surface): cobalt for "posted", brass for "settled".
const COBALT = "#2F4F8A";
const BRASS = "#B08A3E";
const AXIS = "hsl(var(--graphite))";
const GRID = "hsl(var(--rule))";

type TipProps = { active?: boolean; label?: string; payload?: Array<{ name?: string; value?: number; color?: string }> };

function Tip({ active, label, payload, unit }: TipProps & { unit: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[4px] border border-rule-strong bg-sheet px-3 py-2 text-xs shadow-[0_6px_20px_-8px_hsl(var(--ink)/0.25)]">
      <div className="mb-1 font-semibold">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="size-2 rounded-[2px]" style={{ background: p.color }} aria-hidden />
          <span className="text-graphite">{p.name}</span>
          <span className="num ml-auto pl-3 font-medium">
            {sats(p.value ?? 0)} {unit}
            {unit === "sats" ? <PkrNote sats={p.value ?? 0} className="ml-2 font-normal" /> : null}
          </span>
        </div>
      ))}
    </div>
  );
}

const axisProps = { stroke: AXIS, tickLine: false, axisLine: false, fontSize: 12 } as const;

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex gap-4 text-xs text-graphite">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px]" style={{ background: i.color }} aria-hidden />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

export function VolumeView({
  stats,
  volumeData,
  providerData,
  htlcData,
  loading,
}: {
  stats: MarketStats | undefined;
  volumeData: { h: string; v: number }[];
  providerData: { name: string; value: number }[];
  htlcData: { h: string; created: number; settled: number }[];
  loading: boolean;
}) {
  if (loading && !stats) return <EmptyNote>Loading volume from the registry.</EmptyNote>;
  const maxCap = Math.max(1, ...providerData.map((p) => p.value));
  const totalJobs = providerData.reduce((a, p) => a + p.value, 0);

  return (
    <div>
    <BentoGrid>
      <Tile className="p-5 md:p-7" aria-label="Where the sats went">
        <SectionHead title="Where the sats went">Every verified payment, from where it came to where it ended up</SectionHead>
        <div className="mt-6">
          <MoneyFlow
            real={stats?.real_volume_sats ?? 0}
            demo={stats?.demo_volume_sats ?? 0}
            gross={stats?.gross_job_volume_sats ?? 0}
            net={stats?.net_to_sellers_sats ?? 0}
            fee={stats?.platform_fees_sats ?? 0}
          />
        </div>
        <p className="mt-5 max-w-[70ch] text-2xs leading-relaxed text-graphite">
          The 2% platform fee is booked against sellers in the registry; it is not collected on Lightning. Ribbon widths are true to scale; blocks have a
          minimum size so their labels stay readable.
        </p>
      </Tile>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Tile className="p-5">
          <SectionHead title="Sats paid per hour">Most recent 200 jobs</SectionHead>
          {volumeData.some((d) => d.v > 0) ? (
            <WhenSeen className="mt-4 h-[280px]">
              {(animate) => (
              <ResponsiveContainer>
                <BarChart data={volumeData} margin={{ top: 8, right: 4, left: -8, bottom: 0 }} barCategoryGap="28%">
                  <CartesianGrid vertical={false} stroke={GRID} />
                  <XAxis dataKey="h" {...axisProps} />
                  <YAxis {...axisProps} width={48} tickFormatter={(v: number) => sats(v)} />
                  <Tooltip cursor={{ fill: "hsl(var(--ink) / 0.05)" }} content={<Tip unit="sats" />} />
                  <Bar name="Paid" dataKey="v" fill={COBALT} radius={[4, 4, 0, 0]} isAnimationActive={animate} animationDuration={900} animationEasing="ease-out" maxBarSize={36} />
                </BarChart>
              </ResponsiveContainer>
              )}
            </WhenSeen>
          ) : (
            <EmptyNote>Nothing has been paid yet. Settled jobs appear here by the hour.</EmptyNote>
          )}
        </Tile>

        <Tile className="p-5">
          <SectionHead title="Jobs by capability">{totalJobs ? `${sats(totalJobs)} jobs` : null}</SectionHead>
          {providerData.length ? (
            <ul className="mt-5 space-y-4">
              {providerData
                .slice()
                .sort((a, b) => b.value - a.value)
                .map((p) => (
                  <li key={p.name}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="font-medium first-letter:uppercase">{p.name}</span>
                      <span className="num text-graphite">
                        {sats(p.value)} <span className="text-2xs">({Math.round((p.value / totalJobs) * 100)}%)</span>
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 rounded-full bg-rule/70">
                      <div className="muhr-grow h-2 rounded-full" style={{ width: `${(p.value / maxCap) * 100}%`, background: COBALT }} />
                    </div>
                  </li>
                ))}
            </ul>
          ) : (
            <EmptyNote>No jobs yet.</EmptyNote>
          )}
        </Tile>
      </div>

      <Tile className="mt-4 p-5">
        <SectionHead title="Posted and settled, per hour">
          <Legend
            items={[
              { label: "Posted", color: COBALT },
              { label: "Settled", color: BRASS },
            ]}
          />
        </SectionHead>
        {htlcData.length ? (
          <WhenSeen className="mt-4 h-[260px]">
            {(animate) => (
            <ResponsiveContainer>
              <BarChart data={htlcData} margin={{ top: 8, right: 4, left: -8, bottom: 0 }} barGap={2} barCategoryGap="26%">
                <CartesianGrid vertical={false} stroke={GRID} />
                <XAxis dataKey="h" {...axisProps} />
                <YAxis {...axisProps} width={48} allowDecimals={false} />
                <Tooltip cursor={{ fill: "hsl(var(--ink) / 0.05)" }} content={<Tip unit="jobs" />} />
                <Bar name="Posted" dataKey="created" fill={COBALT} radius={[4, 4, 0, 0]} isAnimationActive={animate} animationDuration={900} animationEasing="ease-out" maxBarSize={28} />
                <Bar name="Settled" dataKey="settled" fill={BRASS} radius={[4, 4, 0, 0]} isAnimationActive={animate} animationBegin={180} animationDuration={900} animationEasing="ease-out" maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
            )}
          </WhenSeen>
        ) : (
          <EmptyNote>No jobs yet.</EmptyNote>
        )}
      </Tile>
    </BentoGrid>
    </div>
  );
}
