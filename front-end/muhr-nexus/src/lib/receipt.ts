import type { ReceiptResponse } from "@/types/api";

const HEX64 = /^[0-9a-fA-F]{64}$/;

export function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function bytesToHex(bytes: ArrayBuffer | Uint8Array): string {
  return Array.from(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 of the bytes a hex string encodes, as lowercase hex. Uses the browser's Web Crypto API. */
export async function sha256OfHex(hex: string): Promise<string> {
  const data = hexToBytes(hex);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer);
  return bytesToHex(digest);
}

export type ReceiptCheck =
  /** sha256(preimage) equals the invoice's payment hash: the payment really happened. */
  | { state: "verified"; computed: string }
  /** The preimage is present but does not hash to the payment hash. */
  | { state: "mismatch"; computed: string }
  /** No preimage on this receipt (the seller's wallet confirmed payment instead). */
  | { state: "no-preimage" }
  /** The receipt's fields are not the 32-byte hex values they should be. */
  | { state: "malformed" };

/** Checks sha256(preimage) == payment_hash, entirely in the browser. */
export async function verifyReceipt(r: Pick<ReceiptResponse, "preimage" | "payment_hash">): Promise<ReceiptCheck> {
  if (!r.preimage) return { state: "no-preimage" };
  if (!HEX64.test(r.preimage) || !HEX64.test(r.payment_hash)) return { state: "malformed" };
  const computed = await sha256OfHex(r.preimage);
  return computed === r.payment_hash.toLowerCase() ? { state: "verified", computed } : { state: "mismatch", computed };
}

export function receiptPath(jobId: string): string {
  return `/receipt/${encodeURIComponent(jobId)}`;
}

export function receiptUrl(jobId: string, origin = typeof window !== "undefined" ? window.location.origin : ""): string {
  return `${origin}${receiptPath(jobId)}`;
}
