# MDK Agent Wallet (Buyer MCP)

Real Lightning in Muhr uses [@moneydevkit/agent-wallet](https://www.npmjs.com/package/@moneydevkit/agent-wallet): JSON on stdout, no API keys, local daemon (default `localhost:3456`).

## Prerequisites

- **Node.js** (includes `npx` on your PATH)
- One-time: `npx @moneydevkit/agent-wallet@0.22.0 init` (back up the mnemonic)

## Environment (repo root `.env`)

- `DEMO_MODE=false` to enable MDK
- `MDK_AGENT_WALLET_PACKAGE` (optional): overrides the pinned default `@moneydevkit/agent-wallet@0.22.0`. Always use an exact version, never `@latest`; this CLI runs with access to your wallet.
- `MDK_WALLET_MNEMONIC` / `MDK_WALLET_PORT` — see [Moneydevkit agent wallet](https://docs.moneydevkit.com/agent-wallet)

## MCP tools

- `wallet_status` — runs `balance` via MDK when `DEMO_MODE=false` and `npx` is available.
- `lightning_send` — real `send` to a bolt11 / lightning address / LNURL / BOLT12.
- `send_encrypted_job` runs the full job. The seller returns its result encrypted, together with a per-job BOLT-11. The buyer decodes the invoice and checks its amount and hash against the registry before MDK pays it. The seller then releases the result key once its own MDK wallet shows the payment.

## Job flow and the Lightning lock

No separate HTLC API is needed: the seller's per-job invoice *is* the lock. MDK's `send` returns only a `payment_hash` (no preimage), so in REAL mode the seller confirms receipt with `payments` before releasing the result key. See `docs/PAYMENT_REALITY.md`.

## Prove one real payment

1. Fund the MDK wallet (per MDK network you chose at init, e.g. signet / mainnet).
2. Get a test invoice (e.g. from a second wallet or a faucet that returns bolt11).
3. Run:

```bash
python scripts/mdk_prove_send.py --destination "lnbc..." --amount-sats 1
```

With env `DEMO_MODE=false` in `.env` (or set for the command only on Windows: `$env:DEMO_MODE="false"` before `python`).

## Signet before mainnet (free "test" sats)

MDK only documents two networks: **`mainnet`** and **`signet`**. There is no `testnet3` mode in the CLI. Signet is Bitcoin's public signet chain (play money you can get from faucets) — not the same as classic "testnet" coins.

You can only have **one** active profile in `~/.mdk-wallet` at a time (same machine), so moving to Signet means **replacing** that folder after a backup.

1. **Back up the current wallet** (mainnet): run `scripts/backup_mdk_wallet.ps1` and keep the `~/.mdk-wallet` copy safe.
2. **Stop the daemon:** `npx -y @moneydevkit/agent-wallet@0.22.0 stop`
3. **Remove or rename** `%USERPROFILE%\.mdk-wallet` (only after you are sure you have the mnemonic / backup).
4. **Initialize on Signet:**
   `npx -y @moneydevkit/agent-wallet@0.22.0 init --network signet`
   Save the new mnemonic.
5. **Start and check:** `start` then `balance` (should show `0` until funded).
6. **Get Signet on-chain coins** from a **Bitcoin Signet** faucet, send to the on-chain address your workflow uses, then open channels / use Lightning as MDK expects for that network. Invoices from `receive` will be **Signet Lightning** (often `lntb` / `tbs` style prefixes, not `lnbc` mainnet).
7. **Muhr:** same as mainnet — repo-root `DEMO_MODE=false`, `wallet_status` / `lightning_send` call the same `npx` MDK; they follow whatever network is in the active `~/.mdk-wallet`.

**While you wait for mainnet:** you can also leave **`DEMO_MODE=true`** in `.env` so registry/sellers work without any Lightning; that does not move real or signet sats.

**Switch back to mainnet later:** back up the Signet `~/.mdk-wallet`, restore your saved mainnet folder (or `init` and restore from mainnet mnemonic per MDK docs).
