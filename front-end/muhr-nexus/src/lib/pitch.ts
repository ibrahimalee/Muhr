import type { FeedEvent } from "@/types/api";

/** The eight stages the pitch tracker lights up, each tied to the registry event that marks it. */
export const PITCH_STAGES = [
  { id: "posted", name: "Task posted", event: "task_posted" },
  { id: "committed", name: "Seller committed", event: "commitment" },
  { id: "sealed", name: "Data sealed", event: "data_sent" },
  { id: "delivered", name: "Result delivered", event: "result_delivered" },
  { id: "invoiced", name: "Invoice issued", event: "htlc_opened" },
  { id: "paid", name: "Paid", event: "lightning_paid" },
  { id: "key", name: "Key released", event: "key_released" },
  { id: "settled", name: "Settled", event: "payment_settled" },
] as const;

export type PitchStageId = (typeof PITCH_STAGES)[number]["id"];

export interface PitchPreset {
  id: "urdu" | "summary" | "classify";
  label: string;
  sellerId: string;
  budget: number;
  text: string;
  /** Short line shown under the button. */
  hint: string;
}

export const PITCH_PRESETS: PitchPreset[] = [
  {
    id: "urdu",
    label: "Translate Urdu to English",
    sellerId: "sel_urdu",
    budget: 50,
    text: "آج موسم بہت اچھا ہے اور ہم نے ایک نیا منصوبہ شروع کیا ہے۔ ہمارے گاہک دنیا بھر سے ہیں۔",
    hint: "Urdu translation seller",
  },
  {
    id: "summary",
    label: "Summarise a document",
    sellerId: "sel_summarizer",
    budget: 100,
    text:
      "The services agreement between the supplier and the client runs for twelve months and renews automatically unless either side gives thirty days' notice. " +
      "Fees are invoiced monthly and are due within forty-five days. The supplier's liability is capped at the fees paid in the previous twelve months. " +
      "Either party may terminate early for a material breach that is not fixed within fourteen days of written notice. " +
      "Disputes are handled first by the account managers, then by mediation, and only then in court.",
    hint: "Summariser seller",
  },
  {
    id: "classify",
    label: "Classify items",
    sellerId: "sel_classifier",
    budget: 50,
    text:
      "The patient reported mild chest pain and the doctor ordered an ECG and a blood test.\n" +
      "Invoice 4412 is overdue by thirty days and the loan interest has been added to the balance.\n" +
      "The court set a hearing date for the contract dispute between the two companies.",
    hint: "Classifier seller",
  },
];

export interface PitchTrack {
  taskId: string | null;
  jobId: string | null;
  /** Timestamp per stage (same order as PITCH_STAGES), null while it has not happened. */
  times: (string | null)[];
  /** Number of stages reached. */
  reached: number;
  broken: { kind: "failed" | "timeout" | "dispute"; detail: string | null } | null;
  done: boolean;
}

const BREAK: Record<string, "failed" | "timeout" | "dispute"> = { job_failed: "failed", job_timeout: "timeout", dispute: "dispute" };

export const EMPTY_PITCH_TRACK: PitchTrack = {
  taskId: null,
  jobId: null,
  times: PITCH_STAGES.map(() => null),
  reached: 0,
  broken: null,
  done: false,
};

/**
 * The job a presenter just started: the first `task_posted` event after `fromIndex`, followed
 * through every later event that carries its task or job id. Idle (nothing started) gives an empty track.
 */
export function pitchTrack(events: FeedEvent[], fromIndex: number): PitchTrack {
  const start = events.findIndex((e, i) => i >= fromIndex && e.type === "task_posted");
  if (start < 0) return EMPTY_PITCH_TRACK;
  const taskId = events[start]!.task_id ?? null;
  let jobId: string | null = events[start]!.job_id ?? null;
  const times: (string | null)[] = PITCH_STAGES.map(() => null);
  let broken: PitchTrack["broken"] = null;

  for (let i = start; i < events.length; i++) {
    const e = events[i]!;
    const ours = (taskId && e.task_id === taskId) || (jobId && e.job_id === jobId);
    if (!ours) continue;
    if (!jobId && e.job_id) jobId = e.job_id;
    const idx = PITCH_STAGES.findIndex((s) => s.event === e.type);
    if (idx >= 0 && times[idx] == null) times[idx] = e.timestamp;
    if (BREAK[e.type]) broken = { kind: BREAK[e.type]!, detail: e.detail ?? null };
  }
  const reached = times.filter(Boolean).length;
  return { taskId, jobId, times, reached, broken, done: times[PITCH_STAGES.length - 1] != null };
}
