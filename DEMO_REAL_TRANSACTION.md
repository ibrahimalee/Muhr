# MUHR: running a real transaction (local)

Protocol overview: The buyer never sends a secret to the seller. It seals its input to the seller's X25519 key, receives the result **encrypted** with a per-job invoice, checks the invoice against the registry, pays, and only then gets the result key. See `docs/PAYMENT_REALITY.md`.

## Live evidence: the MDK wallet holds real mainnet sats

### 1. Buyer wallet holds real mainnet sats (inbound LN settlement)

```text
paymentHash : 04a49c8c5dd7d855c3575f725718f9ad4f3435c9cf01f46b70d85002f685165a
amountSats  : 9800
direction   : inbound
status      : completed
network     : mainnet
walletId    : c8833700-1b5b-4ba7-ac24-5a56781a69d3
```

Re-prove live:

```powershell
npx -y @moneydevkit/agent-wallet@0.22.0 balance        # -> 9800 sats, mainnet
npx -y @moneydevkit/agent-wallet@0.22.0 payments       # -> shows the hash above with status=completed
npx -y @moneydevkit/agent-wallet@0.22.0 init --show    # -> network=mainnet, walletId
```

That `paymentHash` was minted by MUHR (the buyer wallet's `receive 10000`),
paid by an external Lightning wallet, and the LSP took 200 sats as the JIT
channel-open fee. That fee getting charged at all is on-network proof that a
real Lightning channel was opened to this wallet.

## DEMO run (no sats move)

```powershell
.\start_all_services.bat                              # registry :8000, sellers :8001/:8002
python scripts\run_real_transaction.py                # prints a JSON receipt
python scripts\run_real_transaction.py --seller sel_classifier --text "The patient has a fever."
```

The dashboard (`cd front-end\muhr-nexus; npm run dev`, then http://127.0.0.1:8080) shows the feed in this order: `task_posted`, `commitment`, `data_sent`, `result_delivered`, `htlc_opened` (invoice issued), `lightning_paid`, `payment_settled`, `reputation_updated`. Its **Run live demo** button calls `POST /api/demo/run_e2e`, where the registry acts as a DEMO buyer.

## REAL run (sats move)

1. Fund the buyer's MDK wallet (`docs/WALLET_FUNDING.md`). The sellers each need their own initialised MDK wallet to receive.
2. In `.env` (read by the registry, sellers and buyer):
   ```
   DEMO_MODE=false
   MUHR_SELLER_KEY_SEL_SUMMARIZER=<long random>
   MUHR_SELLER_KEY_SEL_CLASSIFIER=<long random>
   MUHR_ADMIN_KEY=<long random>
   ```
   Outside DEMO, the built-in sellers keep their seeded stake. Sellers registered through the API start at 0 until you credit a verified deposit with `POST /api/sellers/{id}/stake` and `X-Muhr-Admin-Key`.
3. Restart the services, then run:
   ```powershell
   python scripts\run_real_transaction.py --real --budget 50
   ```
   The receipt shows `mode: REAL`, the invoice `payment_hash`, and the buyer wallet balance before and after. The seller releases the result key once its own `payments` shows the invoice as completed (`payment_verified_by: seller_wallet`).

## MCP client (buyer MCP)

Point your MCP client's server config at `scripts/run_buyer_mcp.py` (same command and args, absolute path). The tools are `find_sellers`, `post_task`, then `send_encrypted_job` (with the `task_id` from `post_task`), plus `wallet_status`, `lightning_send` and `request_human_approval`.

## Troubleshooting

- **401 from the registry:** the seller key differs between the seller (`MUHR_SELLER_KEY`) and the registry (`MUHR_SELLER_KEY_<ID>`). In DEMO both fall back to the same dev key.
- **"Refusing to pay":** the invoice doesn't match what the seller committed at the registry. That's the safety check working.
- **"Seller issued a REAL invoice but this buyer wallet is in DEMO mode":** set `DEMO_MODE=false` on the buyer too, or `true` on the seller.
