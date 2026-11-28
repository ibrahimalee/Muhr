import type { FeedEvent, JobSummary } from "@/types/api";

export function sats(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "–";
  return n.toLocaleString("en-US");
}

/** "a1b2c3d4…e5f6" style truncation for hashes and ids. */
export function shortHash(value: string | null | undefined, head = 8, tail = 6): string {
  if (!value) return "–";
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

export function capabilityLabel(cap: string | null | undefined): string {
  if (!cap) return "Unknown capability";
  const s = cap.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "–";
  const s = Math.round((now - t) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function seconds(ms: number): string {
  if (!ms) return "–";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/* ------------------------------------------------------------------ */
/* Job lifecycle                                                       */
/* ------------------------------------------------------------------ */

export type StageId = "posted" | "quoted" | "sealed" | "committed" | "invoiced" | "paid" | "settled";

export const STAGES: { id: StageId; name: string; note: string; event: string }[] = [
  { id: "posted", name: "Posted", note: "Buyer posts a task with a budget", event: "task_posted" },
  { id: "quoted", name: "Quoted", note: "Seller commits to its pipeline and price", event: "commitment" },
  { id: "sealed", name: "Input sealed", note: "Data encrypted to the seller's key", event: "data_sent" },
  { id: "committed", name: "Result committed", note: "Encrypted result, hashes on record", event: "result_delivered" },
  { id: "invoiced", name: "Invoice issued", note: "Checked against the registry", event: "htlc_opened" },
  { id: "paid", name: "Paid", note: "Payment releases the result key", event: "lightning_paid" },
  { id: "settled", name: "Settled", note: "Fee booked, reputation updated", event: "payment_settled" },
];

/** Index of the last stage a job row has reached (failed/timeout rows: how far they got). */
export function stageOfJob(job: JobSummary): number {
  switch (job.status) {
    case "pending":
      return 0;
    case "committed":
      return 1;
    case "data_sent":
      return 2;
    case "delivered":
      return job.payment_verified ? 5 : 4;
    case "settled":
      return 6;
    default:
      if (job.payment_verified) return 5;
      if (job.delivered_at || job.result_hash) return 4;
      if (job.committed_at) return 1;
      return 0;
  }
}

export type JobTrack = {
  jobId: string | null;
  capability: string | null;
  amount: number | null;
  /** Index of the last stage reached, -1 when nothing has happened. */
  reached: number;
  /** Timestamp per stage index, when known from the feed. */
  times: (string | null)[];
  broken: { kind: "failed" | "timeout" | "dispute"; detail: string | null } | null;
  mode: string | null;
};

const BREAK_EVENTS: Record<string, "failed" | "timeout" | "dispute"> = {
  job_failed: "failed",
  job_timeout: "timeout",
  dispute: "dispute",
};

/**
 * Work out where the most recent job is, preferring live feed events (which carry
 * timestamps per stage) and falling back to the job row's status.
 */
export function latestJobTrack(events: FeedEvent[], jobs: JobSummary[] | undefined): JobTrack {
  const times: (string | null)[] = STAGES.map(() => null);
  const empty: JobTrack = { jobId: null, capability: null, amount: null, reached: -1, times, broken: null, mode: null };

  // The newest event that belongs to a job or task anchors the track.
  let anchorTask: string | null = null;
  let anchorJob: string | null = null;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]!;
    if (e.job_id || e.task_id) {
      anchorJob = e.job_id ?? null;
      anchorTask = e.task_id ?? null;
      break;
    }
  }

  const row = anchorJob
    ? jobs?.find((j) => j.job_id === anchorJob)
    : anchorTask
      ? jobs?.find((j) => j.task_id === anchorTask)
      : jobs?.[0];

  if (!row && !anchorJob && !anchorTask) return empty;

  const jobId = row?.job_id ?? anchorJob;
  const taskId = row?.task_id ?? anchorTask;
  const related = events.filter((e) => (jobId && e.job_id === jobId) || (taskId && e.task_id === taskId));

  let reached = row ? stageOfJob(row) : -1;
  let broken: JobTrack["broken"] = null;
  let mode = row?.lightning_mode ?? null;
  let amount = row?.accepted_price_sats ?? row?.budget_sats ?? null;
  let capability = row?.capability ?? null;

  for (const e of related) {
    const idx = STAGES.findIndex((s) => s.event === e.type);
    if (idx >= 0) {
      times[idx] = e.timestamp;
      if (idx > reached) reached = idx;
    }
    if (BREAK_EVENTS[e.type]) broken = { kind: BREAK_EVENTS[e.type]!, detail: e.detail ?? null };
    if (e.lightning_mode) mode = e.lightning_mode;
    if (e.amount_sats != null && amount == null) amount = e.amount_sats;
    if (e.capability && !capability) capability = e.capability;
  }
  if (row && (row.status === "failed" || row.status === "timeout") && !broken) {
    broken = { kind: row.status, detail: null };
  }
  // Fill timestamps we can read off the job row.
  if (row) {
    times[0] ??= row.created_at;
    if (reached >= 1) times[1] ??= row.committed_at;
    if (reached >= 3) times[3] ??= row.delivered_at;
    if (reached >= 6) times[6] ??= row.settled_at;
  }

  return { jobId, capability, amount, reached, times, broken, mode };
}

export type StatusTone = "settled" | "pending" | "broken" | "neutral";

export function statusTone(status: string): StatusTone {
  if (status === "settled") return "settled";
  if (status === "failed" || status === "timeout") return "broken";
  if (status === "committed" || status === "data_sent" || status === "delivered" || status === "pending") return "pending";
  return "neutral";
}

export function statusLabel(status: string): string {
  switch (status) {
    case "data_sent":
      return "Working";
    case "delivered":
      return "Awaiting payment";
    case "committed":
      return "Quoted";
    case "timeout":
      return "Timed out";
    default:
      return status.charAt(0).toUpperCase() + status.slice(1);
  }
}

export const EVENT_LABELS: Record<string, string> = {
  task_posted: "Task posted",
  commitment: "Seller quoted",
  data_sent: "Sealed input received",
  result_delivered: "Encrypted result committed",
  htlc_opened: "Invoice issued",
  lightning_paid: "Invoice paid",
  payment_settled: "Job settled",
  reputation_updated: "Reputation updated",
  stake_slashed: "Stake slashed",
  stake_deposited: "Stake deposited",
  stake_withdrawn: "Stake withdrawn",
  job_failed: "Job failed",
  job_timeout: "Job timed out",
  dispute: "Dispute filed",
  approval_requested: "Approval requested",
  approval_decided: "Approval decided",
};

export function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? capabilityLabel(type);
}

export type EventTone = "money" | "bad" | "plain";

export function eventTone(type: string): EventTone {
  if (type === "lightning_paid" || type === "payment_settled" || type === "stake_deposited") return "money";
  if (type === "stake_slashed" || type === "job_failed" || type === "job_timeout" || type === "dispute") return "bad";
  return "plain";
}
