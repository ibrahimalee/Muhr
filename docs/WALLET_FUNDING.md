# MDK Wallet funding — three-step runbook

The Muhr 11-step flow can move real Lightning sats at step 11. To do that the
buyer's MDK Agent Wallet has to actually hold sats. This doc lays out two
proven funding paths and the gotchas to watch for.

> **TL;DR:** if you don't want to install MDK, leave `DEMO_MODE=true`
> in `.env`. The 11-step flow still runs end-to-end, the registry still slashes
> stake on hash mismatches, and the live feed still displays the synthetic
> `payment_hash`. The only difference is that no on-chain settlement happens.

---

## Path A — Mainnet small (recommended for the live demo)

Cost: a few sats from any external Lightning wallet (Phoenix, Wallet of
Satoshi, Cash App, etc.). This is the most reliable path because mainnet
liquidity is everywhere.

```powershell
# 1. One-time install of MDK Agent Wallet (Node.js / npx required)
npx -y @moneydevkit/agent-wallet@0.22.0 init
# Save the mnemonic somewhere safe; it is the only recovery key.

# 2. Generate a small invoice from the buyer wallet (e.g. 5000 sats)
npx -y @moneydevkit/agent-wallet@0.22.0 receive 5000

# 3. Pay that bolt11 from any external Lightning wallet.
#    Confirm balance shows up:
npx -y @moneydevkit/agent-wallet@0.22.0 balance
```

Expected output of `balance` once the deposit confirms:

```json
{ "balance_sats": 5000, "network": "mainnet" }
```

After that you can run:

```powershell
$env:DEMO_MODE="false"
python scripts/run_real_transaction.py
```

…and the seller's per-job invoice (issued by `/job`) will return a real BOLT-11 that the
buyer's wallet pays through `lightning_send`. The registry receives the actual
`payment_hash` from MDK and persists it on the Job row, so the dashboard shows
"REAL" mode plus the on-network proof next to the settle event.

---

## Path B — Signet (free play money, but quirky)

Use this when you want to demo without spending real sats. The big footgun is
that **on-chain Signet coins (`tb1…` addresses) do NOT show up as Lightning
balance in MDK** — you need a Signet *Lightning* invoice that's paid through
an LSP-aware faucet.

```powershell
# 1. Switch MDK to signet
npx -y @moneydevkit/agent-wallet@0.22.0 stop
Move-Item "$env:USERPROFILE\.mdk-wallet" "$env:USERPROFILE\.mdk-wallet.mainnet-keep"
npx -y @moneydevkit/agent-wallet@0.22.0 init --network signet

# 2. Generate a signet invoice (note the lntbs… prefix)
npx -y @moneydevkit/agent-wallet@0.22.0 receive 5000

# 3. Pay that invoice from a Signet LSP faucet (search "Mutiny LSP signet faucet"
#    or the equivalent at the time). Do NOT use a tb1 on-chain faucet — those
#    coins land outside the LN channel and balance stays zero.
npx -y @moneydevkit/agent-wallet@0.22.0 balance
```

Once balance > 0 on Signet, the rest of the flow is identical. See also
`buyer_mcp/docs/MDK_NETWORK_SWITCH.md` for switching wallets safely.

---

## Path C — Stay in DEMO_MODE (no funding required)

```powershell
# .env
DEMO_MODE=true
```

In DEMO_MODE the seller's `/job` returns a deterministic non-payable
`lnbc…demo…muhr` string with a synthetic 64-char `payment_hash`. The buyer's
`pay_bolt11` short-circuits and returns the same hash as the "proof". Every
other step (commitment, encryption, hash verification, slashing on mismatch,
SSE feed, dashboard tiles) behaves identically to REAL mode, just labelled
`mode: DEMO` on the registry side.

This is the path used by the automated tests in `tests/` and by the smoke test
`scripts/test_e2e_smoke.py`.

---

## Verifying the wire

After a single successful job in REAL mode:

```powershell
curl http://localhost:8000/api/jobs?limit=1 | python -m json.tool
```

The most recent job should have:

- `lightning_mode = "REAL"`
- `lightning_payment_hash` = 64-char hex (matches MDK's record)
- `status = "settled"`

…and the SSE feed (`/api/feed`) carries an `EVENT_LIGHTNING_PAID` event with the
same proof, plus `EVENT_PAYMENT_SETTLED` with the proof attached. The Nexus UI
renders both rows next to each other.

If you see `lightning_mode = "DEMO"` while you're trying to demo REAL mode,
re-check:

1. `DEMO_MODE=false` in `.env` (the same one Uvicorn started with).
2. `npx --version` works in the same shell that started the buyer MCP.
3. `npx -y @moneydevkit/agent-wallet@0.22.0 balance` returns non-zero.
4. The seller you're running `send_encrypted_job` against was started with the
   same `.env`, so its `/job` invoice also returned `mode: REAL`.
