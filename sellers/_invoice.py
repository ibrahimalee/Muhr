"""Seller-side Lightning: issue invoices and check whether they were paid.

- DEMO: the seller generates the preimage itself, so the invoice hash locks the
  result key (``K = HKDF(preimage)``). The invoice is a ``muhrdemo:`` string that
  no wallet can pay; ``/demo/pay`` stands in for the network.
- REAL: MDK ``receive`` (pinned version). MDK does not reveal the preimage, so the
  result key is random and released once ``payments`` shows the invoice settled.
  A REAL-mode MDK failure is an error: it never silently falls back to DEMO.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Any, Optional

from shared import bolt11, constants, crypto_utils

logger = logging.getLogger(__name__)


class InvoiceFailed(Exception):
    pass


@dataclass
class Invoice:
    bolt11: str
    payment_hash: str
    amount_sats: int
    mode: str                      # REAL | DEMO
    preimage: Optional[bytes]      # known only in DEMO


async def mdk_json(*args: str, timeout: float = 60.0) -> Any:
    npx = shutil.which("npx")
    if not npx:
        raise InvoiceFailed("npx not on PATH (install Node.js for MDK)")
    proc = await asyncio.create_subprocess_exec(npx, "-y", constants.mdk_package(), *args,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                env={**os.environ})
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise InvoiceFailed(f"MDK {args[0]} timed out")
    out = (out_b or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode not in (0, None) or not out:
        err = (err_b or b"").decode("utf-8", errors="replace").strip()
        raise InvoiceFailed(f"MDK {args[0]} failed: {err[-300:] or f'exit {proc.returncode}'}")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise InvoiceFailed(f"MDK output not JSON: {e}") from e


def _pick(d: dict, *keys: str) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return None


async def create_invoice(amount_sats: int, memo: str) -> Invoice:
    if amount_sats < 1:
        raise InvoiceFailed("amount must be >= 1 sat")
    if constants.demo_mode():
        pre = crypto_utils.generate_preimage()
        ph = crypto_utils.compute_payment_hash(pre)
        return Invoice(bolt11.make_demo_invoice(amount_sats, ph), ph, amount_sats, "DEMO", pre)

    r = await mdk_json("receive", str(int(amount_sats)), "--description", memo[:100])
    if not isinstance(r, dict):
        raise InvoiceFailed("unexpected MDK receive output")
    inv = _pick(r, "invoice", "bolt11", "payment_request")
    if not inv:
        raise InvoiceFailed(f"MDK receive returned no invoice: {str(r)[:200]}")
    decoded = bolt11.decode(inv)  # never trust a reported hash/amount over the invoice itself
    if decoded.amount_sat != amount_sats:
        raise InvoiceFailed(f"MDK invoice amount {decoded.amount_sat} != {amount_sats}")
    reported = _pick(r, "payment_hash", "paymentHash", "rhash")
    if reported and reported.lower() != decoded.payment_hash:
        raise InvoiceFailed("MDK reported payment_hash does not match the invoice")
    return Invoice(inv, decoded.payment_hash, amount_sats, "REAL", None)


_DONE = {"completed", "complete", "succeeded", "success", "settled", "paid"}
_INBOUND = {"inbound", "incoming", "receive", "received", "in"}


async def invoice_paid(payment_hash: str) -> bool:
    """REAL mode: does this seller's MDK wallet show the invoice as received?"""
    try:
        r = await mdk_json("payments", timeout=30.0)
    except InvoiceFailed as e:
        logger.warning("MDK payments check failed: %s", e)
        return False
    rows = r.get("payments", r) if isinstance(r, dict) else r
    if not isinstance(rows, list):
        return False
    for p in rows:
        if not isinstance(p, dict):
            continue
        h = (_pick(p, "payment_hash", "paymentHash") or "").lower()
        if h != payment_hash.lower():
            continue
        status = (_pick(p, "status", "state") or "").lower()
        direction = (_pick(p, "direction", "type") or "inbound").lower()
        if status in _DONE and direction in _INBOUND:
            return True
    return False
