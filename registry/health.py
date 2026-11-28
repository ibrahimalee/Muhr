"""Seller health checks.

Network probes run with no DB session open; results are applied afterwards in
one short transaction. Inactive sellers are probed too, so a seller that comes
back is reactivated. Suspended sellers (stake below minimum) are left alone.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from registry import database
from registry.models import Seller, SellerStatus, utcnow
from shared import constants
from shared.http import async_client

logger = logging.getLogger(__name__)


async def _probe(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(f"{url.rstrip('/')}{constants.API_SELLER_HEALTH}")
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def health_check_all_sellers() -> dict[str, bool]:
    with database.get_db() as db:
        targets = [
            (s.seller_id, s.endpoint_url)
            for s in db.query(Seller).filter(Seller.status.in_([SellerStatus.ACTIVE, SellerStatus.INACTIVE])).all()
            if s.seller_id != "sel_platform"
        ]

    async with async_client(timeout=constants.HEALTH_CHECK_TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(*[_probe(client, url) for _, url in targets])
    outcome = {sid: ok for (sid, _), ok in zip(targets, results)}

    with database.get_db() as db:
        for sid, ok in outcome.items():
            seller = db.get(Seller, sid)
            if seller is None or seller.status == SellerStatus.SUSPENDED:
                continue
            if ok:
                seller.consecutive_failures = 0
                seller.last_seen = utcnow()
                if seller.status == SellerStatus.INACTIVE:
                    seller.status = SellerStatus.ACTIVE
                    logger.info("Seller %s reactivated (health OK)", sid)
            else:
                seller.consecutive_failures = (seller.consecutive_failures or 0) + 1
                if seller.consecutive_failures >= constants.MAX_CONSECUTIVE_FAILURES and seller.status == SellerStatus.ACTIVE:
                    seller.status = SellerStatus.INACTIVE
                    logger.warning("Seller %s marked INACTIVE after %s failures", sid, seller.consecutive_failures)
    return outcome


def health_check_all_sellers_sync() -> None:
    try:
        asyncio.run(health_check_all_sellers())
    except Exception as e:  # noqa: BLE001
        logger.error("Health check error: %s", e)
