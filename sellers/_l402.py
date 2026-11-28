"""L402-style macaroons for the seller's ``/key`` endpoint.

The macaroon is HMAC-signed by the seller and binds ``job_id`` + ``payment_hash``,
so it cannot be forged or moved to another job. Presenting
``Authorization: L402 <macaroon>:<preimage_hex>`` proves payment of that invoice.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import HTTPException

from shared.crypto_utils import preimage_matches

_SECRET = (os.getenv("MUHR_L402_SECRET", "").encode() or secrets.token_bytes(32))


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_macaroon(*, job_id: str, amount_sats: int, payment_hash: str) -> str:
    body = _b64u(json.dumps({"job_id": job_id, "amount_sats": int(amount_sats), "payment_hash": payment_hash,
                             "issued_at": int(time.time())}, sort_keys=True, separators=(",", ":")).encode())
    sig = _b64u(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_macaroon(macaroon: str) -> dict:
    try:
        body, sig = macaroon.rsplit(".", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="L402: malformed macaroon")
    expected = _b64u(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="L402: macaroon signature invalid")
    return json.loads(_b64u_decode(body))


def parse_authorization(header: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not header or not header.strip().lower().startswith("l402 "):
        return None, None
    rest = header.strip()[5:].strip()
    if ":" not in rest:
        return None, None
    mac, pre = rest.rsplit(":", 1)
    return mac.strip(), pre.strip()


def check_l402(header: Optional[str], *, job_id: str, payment_hash: str) -> Optional[str]:
    """Return the verified preimage hex if a valid L402 header is present, else None."""
    mac, pre = parse_authorization(header)
    if not mac:
        return None
    payload = verify_macaroon(mac)
    if payload.get("job_id") != job_id or payload.get("payment_hash") != payment_hash:
        raise HTTPException(status_code=403, detail="L402: macaroon is for a different job")
    if not preimage_matches(pre or "", payment_hash):
        raise HTTPException(status_code=403, detail="L402: preimage does not hash to payment_hash")
    return pre


__all__ = ["check_l402", "issue_macaroon", "parse_authorization", "verify_macaroon"]
