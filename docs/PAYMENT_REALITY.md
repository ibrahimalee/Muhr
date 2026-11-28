# Payment reality: what is real, what is ledger, what is simulated

This describes how payment works in the registry (`2.0.0`).

## The lock

The only lock is the seller's per-job invoice. Its `payment_hash` is stored as `jobs.payment_hash` when the seller calls `/complete`. Before paying, the buyer checks that the invoice it received decodes to exactly that hash and to the agreed price.

## How paying releases the result

| Key release | When | How the buyer gets `K` | How the registry verifies payment |
| --- | --- | --- | --- |
| `preimage` | DEMO; any wallet that exposes the payment preimage | `K = HKDF(preimage, job_id)` | `sha256(preimage) == payment_hash` |
| `seller_confirmed` | REAL with MDK (its `send` returns only `payment_hash`) | `POST seller/key`. The seller releases `K` once its own MDK `payments` shows the invoice settled (or an L402 preimage is presented) | The seller calls `/payment/confirm` with its seller key |

Before payment, the seller commits `sha256(result)`, `sha256(K)` and `sha256(ciphertext)` to the registry. If the buyer pays and the result doesn't decrypt to the committed hash, `POST /dispute` lets the registry check that from the evidence and slash 50%.

**Remaining trust assumption (`seller_confirmed` only).** A seller that is paid but never releases `K` gets slashed through the dispute path. But if it denies having been paid, the registry can't prove otherwise without a preimage. A wallet that returns preimages removes this gap.

## Component status

| Component | Status |
| --- | --- |
| Buyer pays seller BOLT-11 (`DEMO_MODE=false`) | **REAL.** Pinned MDK CLI. The amount and hash are checked before `send`. |
| Seller invoice per job | **REAL.** MDK `receive`; failure aborts the job (no silent DEMO fallback). |
| Payment verification at the registry | **REAL.** A preimage proof or the seller's wallet confirmation, recorded exactly once. |
| Input confidentiality from the registry | **REAL.** X25519 sealed box. The registry stores sizes only. |
| Input confidentiality from LLM providers | **None** when `GROQ_API_KEY`/`GEMINI_API_KEY` are set. **Offline** otherwise. |
| `--network=none` processing | **REAL** with `MUHR_SELLER_ISOLATION=docker`. |
| Stake | **Ledger.** DEMO grants 10k. Outside DEMO, only the operator credits verified deposits. |
| Platform fee | **Ledger.** 2% is accrued against the seller, not collected on Lightning. |
| DEMO invoices | **Synthetic.** `muhrdemo:<sats>:<hash>`, settled by the seller's `/demo/pay`. |
