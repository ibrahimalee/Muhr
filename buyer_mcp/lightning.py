"""Buyer Lightning wallet: MDK Agent Wallet CLI (REAL) or DEMO.

Every payment goes through ``pay_invoice``, which decodes the BOLT-11 and refuses
to pay unless the amount and payment hash are exactly what the buyer expects.
The MDK package version is pinned (see ``shared.constants.mdk_package``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Optional

from shared import bolt11, constants

logger = logging.getLogger(__name__)


class PaymentRefused(Exception):
    """The invoice did not match what the buyer agreed to pay."""


class LightningWallet:
    def __init__(self, demo_mode: Optional[bool] = None) -> None:
        self.demo_mode = constants.demo_mode() if demo_mode is None else demo_mode
        self._npx = shutil.which("npx")
        if not self.demo_mode and not self._npx:
            logger.warning("npx not found (install Node.js). Wallet stays in DEMO mode.")
            self.demo_mode = True
        logger.info("Lightning wallet initialized (demo_mode=%s)", self.demo_mode)

    @property
    def mode(self) -> str:
        return "DEMO" if self.demo_mode else "REAL"

    async def _mdk(self, *args: str, timeout: float = 90.0) -> Any:
        if not self._npx:
            return {"error": "npx not available"}
        proc = await asyncio.create_subprocess_exec(self._npx, "-y", constants.mdk_package(), *args,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                    env={**os.environ})
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": f"MDK {args[0]} timed out"}
        out = (out_b or b"").decode("utf-8", errors="replace").strip()
        err = (err_b or b"").decode("utf-8", errors="replace").strip()
        if not out:
            return {"error": err[-300:] or f"exit {proc.returncode}"}
        try:
            data = json.loads(out)
        except json.JSONDecodeError as e:
            return {"error": f"MDK output not JSON: {e}"}
        if proc.returncode not in (0, None) and isinstance(data, dict) and "error" not in data:
            data["error"] = err[-300:] or f"exit {proc.returncode}"
        return data

    async def wallet_status(self) -> dict:
        if self.demo_mode:
            return {"mode": "DEMO", "balance_sats": None, "detail": "DEMO_MODE: no sats move. Set DEMO_MODE=false for MDK."}
        r = await self._mdk("balance")
        if not isinstance(r, dict) or ("error" in r and "balance_sats" not in r):
            return {"mode": "REAL", "balance_sats": None, "mdk_configured": True,
                    "detail": f"MDK balance failed: {r.get('error') if isinstance(r, dict) else r}"}
        try:
            bal = int(r.get("balance_sats", r.get("balanceSats")))
        except (TypeError, ValueError):
            bal = None
        return {"mode": "REAL", "balance_sats": bal, "mdk_configured": True, "detail": "MDK balance ok", "data": r}

    async def send_lightning(self, destination: str, amount_sats: Optional[int]) -> dict:
        """Free-form send (MCP ``lightning_send`` tool). Bolt11 destinations are decoded first."""
        dest = (destination or "").strip()
        if not dest:
            return {"success": False, "error": "destination required"}
        if self.demo_mode:
            return {"success": False, "error": "DEMO_MODE: set DEMO_MODE=false and initialise MDK to send real sats"}
        if dest.lower().startswith(("lnbc", "lntb", "lntbs", "lnbcrt")):
            try:
                inv = bolt11.decode(dest)
            except bolt11.InvoiceError as e:
                return {"success": False, "error": f"invalid invoice: {e}"}
            if inv.amount_sat is not None and amount_sats is not None and inv.amount_sat != amount_sats:
                return {"success": False, "error": f"invoice is for {inv.amount_sat} sats, not {amount_sats}"}
        args = ["send", dest] + ([str(int(amount_sats))] if amount_sats is not None else [])
        r = await self._mdk(*args)
        if not isinstance(r, dict) or ("error" in r and not any(k in r for k in ("payment_hash", "paymentHash"))):
            return {"success": False, "error": r.get("error") if isinstance(r, dict) else str(r), "data": r}
        return {"success": True, "data": r}

    async def pay_invoice(self, invoice: str, *, expected_amount_sats: int, expected_payment_hash: str,
                          max_amount_sats: int) -> dict:
        """Pay a REAL BOLT-11 after checking amount and hash. Returns {payment_hash, preimage}."""
        try:
            inv = bolt11.decode(invoice)
        except bolt11.InvoiceError as e:
            raise PaymentRefused(f"invalid invoice: {e}") from e
        if inv.demo:
            raise PaymentRefused("demo invoices are settled via the seller's /demo/pay, not the wallet")
        if self.demo_mode:
            raise PaymentRefused("seller issued a REAL invoice but this buyer wallet is in DEMO mode")
        if inv.amount_sat is None:
            raise PaymentRefused("refusing to pay a zero-amount invoice")
        if inv.amount_sat != expected_amount_sats or inv.amount_sat > max_amount_sats:
            raise PaymentRefused(f"invoice amount {inv.amount_sat} != agreed {expected_amount_sats} (max {max_amount_sats})")
        if inv.payment_hash != expected_payment_hash.lower():
            raise PaymentRefused("invoice payment_hash does not match the hash committed at the registry")
        r = await self._mdk("send", invoice)
        if not isinstance(r, dict) or ("error" in r and not any(k in r for k in ("payment_hash", "paymentHash"))):
            raise PaymentRefused(f"MDK send failed: {r.get('error') if isinstance(r, dict) else r}")
        preimage = next((r[k] for k in ("payment_preimage", "preimage", "paymentPreimage") if isinstance(r.get(k), str)), None)
        return {"payment_hash": inv.payment_hash, "preimage": preimage, "raw": r}

    async def close(self) -> None:
        return None
