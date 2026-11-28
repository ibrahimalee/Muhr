"""Ledger helpers: platform fee, stake slashing, reputation.

None of these functions commit. The caller owns the transaction, so a job's
state change and its ledger rows land atomically (or not at all).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from registry.models import Seller, SellerStatus, Transaction, utcnow
from shared import constants

logger = logging.getLogger(__name__)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def calculate_platform_fee(amount_sats: int) -> int:
    return (amount_sats * constants.PLATFORM_FEE_PERCENT) // 100


def record_platform_fee(db: Session, job_id: str, seller_id: str, amount_sats: int) -> int:
    """Accrue the platform fee for a settled job.

    The buyer pays the seller's invoice in full; the 2% is a receivable the
    seller owes the platform. It is recorded against the paying seller (not a
    fake platform account) so the ledger shows who owes it.
    """
    fee = calculate_platform_fee(amount_sats)
    if fee > 0:
        db.add(Transaction(tx_id=new_id("tx"), job_id=job_id, seller_id=seller_id,
                           type="platform_fee", amount_sats=fee, timestamp=utcnow()))
    return fee


def recompute_reputation(seller: Seller) -> None:
    """Bayesian success rate in [0, 100]. Stake is deliberately NOT part of it."""
    ok = seller.jobs_completed or 0
    bad = seller.jobs_failed or 0
    seller.reputation_score = round(100.0 * (ok + 1) / (ok + bad + 2), 2)


def update_response_time(seller: Seller, elapsed_ms: int) -> None:
    """Exponential moving average of delivery latency."""
    if elapsed_ms < 0:
        return
    prev = seller.avg_response_ms or 0
    seller.avg_response_ms = elapsed_ms if prev == 0 else int(prev * 0.8 + elapsed_ms * 0.2)


def slash_stake(db: Session, seller: Seller, percent: int, reason: str, job_id: str | None = None) -> int:
    """Slash ``percent`` of the seller's current stake. Returns sats slashed (no commit)."""
    percent = max(0, min(100, int(percent)))
    amount = (seller.stake_sats * percent) // 100
    seller.stake_sats -= amount
    seller.max_job_value = seller.stake_sats // constants.STAKE_TO_MAX_JOB_RATIO
    seller.jobs_failed = (seller.jobs_failed or 0) + 1
    recompute_reputation(seller)
    db.add(Transaction(tx_id=new_id("tx"), job_id=job_id, seller_id=seller.seller_id,
                       type="stake_slash", amount_sats=-amount, timestamp=utcnow()))
    if seller.stake_sats < constants.MIN_STAKE_SATS:
        seller.status = SellerStatus.SUSPENDED
    logger.warning("Slashed %s%% (%s sats) from %s: %s", percent, amount, seller.seller_id, reason)
    return amount
