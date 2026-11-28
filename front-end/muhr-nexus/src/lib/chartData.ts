import type { JobSummary, SellerInfo } from "@/types/api";

function hourLabel(value: string): string {
  const time = new Date(value);
  return Number.isNaN(time.getTime())
    ? "unknown"
    : `${String(time.getHours()).padStart(2, "0")}:00`;
}

export function buildVolumeFromJobs(jobs: JobSummary[] | undefined): { h: string; v: number }[] {
  const buckets = new Map<string, number>();
  for (const job of jobs ?? []) {
    const key = hourLabel(job.created_at);
    const paid = job.status === "settled" || job.payment_verified;
    const amount = paid ? Math.max(0, job.accepted_price_sats ?? job.budget_sats) : 0;
    buckets.set(key, (buckets.get(key) ?? 0) + amount);
  }
  return [...buckets.entries()].map(([h, v]) => ({ h, v })).reverse();
}

export function buildHtlcFromJobs(jobs: JobSummary[] | undefined): { h: string; created: number; settled: number }[] {
  const buckets = new Map<string, { created: number; settled: number }>();
  for (const job of jobs ?? []) {
    const key = hourLabel(job.created_at);
    const bucket = buckets.get(key) ?? { created: 0, settled: 0 };
    bucket.created += 1;
    if (job.status === "settled") bucket.settled += 1;
    buckets.set(key, bucket);
  }
  return [...buckets.entries()].map(([h, counts]) => ({ h, ...counts })).reverse();
}

export function buildProviderMix(
  jobs: JobSummary[] | undefined,
  sellers: SellerInfo[] | undefined,
): { name: string; value: number }[] {
  const counts = new Map<string, number>();
  for (const seller of sellers ?? []) counts.set(seller.capability, 0);
  for (const job of jobs ?? []) {
    counts.set(job.capability, (counts.get(job.capability) ?? 0) + 1);
  }
  return [...counts.entries()]
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name: name.replace(/_/g, " "), value }));
}
