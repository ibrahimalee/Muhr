import { describe, expect, it } from "vitest";
import { receiptPath, receiptUrl, sha256OfHex, verifyReceipt } from "./receipt";

// Known SHA-256 values of fixed 32-byte inputs (checked against an independent implementation).
const VECTORS: Array<[string, string]> = [
  ["00".repeat(32), "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"],
  ["01".repeat(32), "72cd6e8422c407fb6d098690f1130b7ded7ec2f7f5e1d30bd9d521f015363793"],
  ["ab".repeat(32), "9a2db2e23f1504cd056606553ac049c5e718e8f9ce9233876df1a7a1821af885"],
  ["0123456789abcdef".repeat(4), "4884fdaafea47c29fea7159d0daddd9c085d6200e1359e85bb81736af6b7c837"],
];

describe("sha256OfHex", () => {
  it.each(VECTORS)("hashes %s", async (preimage, hash) => {
    expect(await sha256OfHex(preimage)).toBe(hash);
  });
});

describe("verifyReceipt", () => {
  it("verifies when the preimage hashes to the payment hash", async () => {
    const [preimage, hash] = VECTORS[0]!;
    expect((await verifyReceipt({ preimage, payment_hash: hash })).state).toBe("verified");
  });

  it("accepts an upper-case payment hash", async () => {
    const [preimage, hash] = VECTORS[1]!;
    expect((await verifyReceipt({ preimage, payment_hash: hash.toUpperCase() })).state).toBe("verified");
  });

  it("reports a mismatch when the hash belongs to another preimage", async () => {
    const [preimage] = VECTORS[0]!;
    const [, otherHash] = VECTORS[1]!;
    const r = await verifyReceipt({ preimage, payment_hash: otherHash });
    expect(r.state).toBe("mismatch");
  });

  it("reports a mismatch when one hex digit of the hash is changed", async () => {
    const [preimage, hash] = VECTORS[2]!;
    const tampered = (hash[0] === "0" ? "1" : "0") + hash.slice(1);
    expect((await verifyReceipt({ preimage, payment_hash: tampered })).state).toBe("mismatch");
  });

  it("says so plainly when there is no preimage", async () => {
    expect((await verifyReceipt({ preimage: null, payment_hash: VECTORS[0]![1] })).state).toBe("no-preimage");
  });

  it("rejects values that are not 32-byte hex", async () => {
    expect((await verifyReceipt({ preimage: "xyz", payment_hash: VECTORS[0]![1] })).state).toBe("malformed");
    expect((await verifyReceipt({ preimage: "00".repeat(32), payment_hash: "abc" })).state).toBe("malformed");
  });
});

describe("receipt links", () => {
  it("builds the public path and url", () => {
    expect(receiptPath("job_abc123")).toBe("/receipt/job_abc123");
    expect(receiptUrl("job_abc123", "https://muhr.example")).toBe("https://muhr.example/receipt/job_abc123");
  });
});
