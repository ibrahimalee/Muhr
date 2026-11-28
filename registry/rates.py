"""BTC -> PKR exchange rate for display only (never used to price or settle anything).

Fetched from CoinGecko's public simple-price endpoint (no key) and cached in memory
for ten minutes. If the fetch fails the last good value is served with ``stale`` set;
if there has never been one, the ``MUHR_FALLBACK_BTC_PKR`` value is served. The
endpoint built on this never raises because of the upstream API.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from shared import constants

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
SATS_PER_BTC = 100_000_000

Fetcher = Callable[[], float]


def fetch_btc_pkr() -> float:
    """One upstream request. Raises on any problem; the caller decides what to serve."""
    r = httpx.get(COINGECKO_URL, params={"ids": "bitcoin", "vs_currencies": "pkr"}, timeout=6.0,
                  headers={"Accept": "application/json", "User-Agent": "muhr-registry"})
    r.raise_for_status()
    value = float(r.json()["bitcoin"]["pkr"])
    if not value > 0:
        raise ValueError("non-positive rate")
    return value


class RateCache:
    def __init__(self, fetcher: Fetcher = fetch_btc_pkr, ttl: float = constants.RATES_CACHE_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._fetcher = fetcher
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._btc_pkr: Optional[float] = None
        self._fetched_wall: Optional[datetime] = None
        self._fetched_mono: float = 0.0

    def get(self) -> dict:
        with self._lock:
            fresh = self._btc_pkr is not None and (self._clock() - self._fetched_mono) < self._ttl
            if not fresh:
                try:
                    self._btc_pkr = float(self._fetcher())
                    self._fetched_wall = datetime.now(timezone.utc)
                    self._fetched_mono = self._clock()
                    fresh = True
                except Exception as e:  # noqa: BLE001
                    logger.warning("BTC/PKR rate fetch failed: %s", e.__class__.__name__)
            if self._btc_pkr is not None:
                btc, when = self._btc_pkr, self._fetched_wall
                source = "coingecko"
            else:
                btc, when, source = constants.fallback_btc_pkr(), datetime.now(timezone.utc), "fallback"
            return {
                "btc_pkr": btc,
                "sats_pkr": btc / SATS_PER_BTC,
                "source": source,
                "fetched_at": when.isoformat().replace("+00:00", "Z"),
                "stale": (not fresh) or source == "fallback",
            }


cache = RateCache()
