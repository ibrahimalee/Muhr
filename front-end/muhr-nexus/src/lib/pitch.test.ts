import { describe, expect, it } from "vitest";
import type { FeedEvent } from "@/types/api";
import { EMPTY_PITCH_TRACK, PITCH_PRESETS, PITCH_STAGES, pitchTrack } from "./pitch";

const ev = (type: string, extra: Partial<FeedEvent> = {}): FeedEvent => ({ type, timestamp: `2000-01-01T00:00:0${extra.detail ?? "0"}Z`, ...extra });

const OLD = [
  ev("task_posted", { task_id: "t_old" }),
  ev("commitment", { task_id: "t_old", job_id: "j_old" }),
  ev("payment_settled", { task_id: "t_old", job_id: "j_old" }),
];

describe("pitchTrack", () => {
  it("is empty until the presenter starts a job", () => {
    expect(pitchTrack(OLD, OLD.length)).toEqual(EMPTY_PITCH_TRACK);
    expect(pitchTrack([], 0).reached).toBe(0);
  });

  it("ignores earlier jobs and lights stages as their events arrive", () => {
    const live = [
      ...OLD,
      ev("task_posted", { task_id: "t1" }),
      ev("commitment", { task_id: "t1", job_id: "j1" }),
      ev("data_sent", { task_id: "t1", job_id: "j1" }),
    ];
    const t = pitchTrack(live, OLD.length);
    expect(t.taskId).toBe("t1");
    expect(t.jobId).toBe("j1");
    expect(t.times.map(Boolean)).toEqual([true, true, true, false, false, false, false, false]);
    expect(t.reached).toBe(3);
    expect(t.done).toBe(false);
  });

  it("finishes when the settled event arrives, whatever order the middle events come in", () => {
    const all = PITCH_STAGES.map((s, i) => ev(s.event, { task_id: "t2", job_id: i ? "j2" : undefined }));
    const shuffled = [all[0]!, all[1]!, all[2]!, all[4]!, all[3]!, all[5]!, all[6]!, all[7]!];
    const t = pitchTrack(shuffled, 0);
    expect(t.reached).toBe(8);
    expect(t.done).toBe(true);
  });

  it("does not mix in events from another job that runs at the same time", () => {
    const live = [
      ev("task_posted", { task_id: "a" }),
      ev("commitment", { task_id: "a", job_id: "ja" }),
      ev("task_posted", { task_id: "b" }),
      ev("commitment", { task_id: "b", job_id: "jb" }),
      ev("payment_settled", { task_id: "b", job_id: "jb" }),
    ];
    const t = pitchTrack(live, 0);
    expect(t.taskId).toBe("a");
    expect(t.done).toBe(false);
    expect(t.reached).toBe(2);
  });

  it("reports a stopped job", () => {
    const live = [ev("task_posted", { task_id: "x" }), ev("commitment", { task_id: "x", job_id: "jx" }), ev("job_failed", { task_id: "x", job_id: "jx", detail: "seller offline" })];
    const t = pitchTrack(live, 0);
    expect(t.broken).toEqual({ kind: "failed", detail: "seller offline" });
    expect(t.done).toBe(false);
  });
});

describe("pitch presets", () => {
  it("each preset hires a seller with a short, prefilled input", () => {
    expect(PITCH_PRESETS.map((p) => p.label)).toEqual(["Translate Urdu to English", "Summarise a document", "Classify items"]);
    for (const p of PITCH_PRESETS) {
      expect(p.text.length).toBeGreaterThan(20);
      expect(p.text.length).toBeLessThanOrEqual(5000);
      expect(p.sellerId).toMatch(/^sel_/);
    }
  });
});
