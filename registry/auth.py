"""Authentication and rate limiting for the registry.

Roles:
- **seller**: ``X-Muhr-Seller-Key`` issued at registration (built-in sellers get
  theirs from ``MUHR_SELLER_KEY_<SELLER_ID>``).
- **buyer**: ``X-Muhr-Buyer-Token`` issued per task by ``POST /api/tasks``.
- **operator**: ``X-Muhr-Admin-Key`` matching ``MUHR_ADMIN_KEY``.
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
import time

from fastapi import HTTPException, Request

from registry.models import Seller, Task
from shared import constants, startup
from shared.crypto_utils import token_matches

logger = logging.getLogger(__name__)


def builtin_seller_key(seller_id: str) -> str | None:
    """Shared secret for a built-in seller process.

    Production: set ``MUHR_SELLER_KEY_SEL_SUMMARIZER`` (etc.) on both the
    registry and the seller. DEMO mode falls back to a well-known dev key so the
    quickstart works with zero config; that fallback is refused outside DEMO.
    """
    v = os.getenv(f"MUHR_SELLER_KEY_{seller_id.upper()}", "").strip()
    if v:
        return v
    if not startup.strict():
        return f"dev-insecure-key-{seller_id}"
    return None


def require_seller(request: Request, seller: Seller | None) -> Seller:
    if seller is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    key = request.headers.get(constants.HEADER_SELLER_KEY)
    if not token_matches(key, seller.api_key_hash):
        raise HTTPException(status_code=401, detail=f"Missing or invalid {constants.HEADER_SELLER_KEY} for {seller.seller_id}")
    return seller


def require_buyer(request: Request, task: Task | None) -> Task:
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    token = request.headers.get(constants.HEADER_BUYER_TOKEN)
    if not token_matches(token, task.buyer_token_hash):
        raise HTTPException(status_code=401, detail=f"Missing or invalid {constants.HEADER_BUYER_TOKEN}")
    return task


def require_admin(request: Request) -> None:
    expected = os.getenv("MUHR_ADMIN_KEY", "").strip()
    if not expected:
        if not startup.strict():
            return  # local DEMO convenience; a public or non-DEMO deployment must set the key
        raise HTTPException(status_code=503, detail="MUHR_ADMIN_KEY is not configured on this registry")
    got = request.headers.get(constants.HEADER_ADMIN_KEY, "")
    if not hmac.compare_digest(got.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail=f"Missing or invalid {constants.HEADER_ADMIN_KEY}")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def client_ip(request: Request) -> str:
    """Client IP. ``X-Forwarded-For`` is only trusted behind our own proxy, and then
    the *last* hop (the address nginx saw) is used, which a client cannot forge."""
    if constants.env_flag("MUHR_TRUST_PROXY", False):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RateLimiter:
    def __init__(self, max_keys: int = 10_000) -> None:
        self._hits: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def allow(self, bucket: str, ip: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        key = (bucket, ip)
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if t >= cutoff]
            allowed = len(hits) < max_requests
            if allowed:
                hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > self._max_keys:
                self._prune(cutoff)
        return allowed

    def _prune(self, cutoff: float) -> None:
        for k in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
            del self._hits[k]
        while len(self._hits) > self._max_keys:  # still too many: drop arbitrary oldest
            self._hits.pop(next(iter(self._hits)))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()

# path -> (bucket, env var, default per minute)
RATE_LIMITS: dict[str, tuple[str, str, int]] = {
    constants.API_SELLERS_REGISTER: ("register", "MUHR_RATE_LIMIT_REGISTER_PER_MIN", 10),
    constants.API_APPROVE: ("approve", "MUHR_RATE_LIMIT_APPROVE_PER_MIN", 60),
    constants.API_TASKS: ("tasks", "MUHR_RATE_LIMIT_TASKS_PER_MIN", 120),
    "/api/demo/run_e2e": ("demo", "MUHR_RATE_LIMIT_DEMO_PER_MIN", 6),
}
