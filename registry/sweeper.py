"""Deadline enforcement: task expiry, delivery timeouts (slashed), unpaid invoices, auto-settle."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from registry import database
from registry.lightning import record_platform_fee, recompute_reputation, slash_stake
from registry.models import Job, JobStatus, Seller, Task, utcnow
from registry.sse import broadcaster
from shared import constants, schemas

logger = logging.getLogger(__name__)


def _event(type_: str, job: Job, detail: str, amount: int | None = None) -> schemas.FeedEvent:
    return schemas.FeedEvent(type=type_, timestamp=utcnow(), job_id=job.job_id, task_id=job.task_id,
                             seller_id=job.seller_id, capability=job.capability,
                             amount_sats=job.budget_sats if amount is None else amount, detail=detail)


def settle_job_row(db, job: Job, seller: Seller | None, now: datetime) -> int:
    """Shared by the settle endpoint and auto-settle. Caller commits."""
    job.status = JobStatus.SETTLED
    job.settled_at = now
    fee = record_platform_fee(db, job.job_id, job.seller_id, job.accepted_price_sats or job.budget_sats)
    if seller is not None:
        seller.jobs_completed = (seller.jobs_completed or 0) + 1
        recompute_reputation(seller)
    task = db.get(Task, job.task_id)
    if task is not None:
        task.status = constants.TASK_DONE
    return fee


def run_sweeper(now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    counts = {"tasks_expired": 0, "commit_timeouts": 0, "delivery_timeouts": 0, "unpaid": 0, "auto_settled": 0}
    events: list[schemas.FeedEvent] = []
    with database.get_db() as db:
        for task in db.query(Task).filter(Task.status == constants.TASK_OPEN, Task.expires_at < now).all():
            task.status = constants.TASK_EXPIRED
            counts["tasks_expired"] += 1

        # Buyer never sent data: not the seller's fault, no slash.
        limit = now - timedelta(seconds=constants.HTLC_TIMEOUT_SECONDS)
        for job in db.query(Job).filter(Job.status == JobStatus.COMMITTED, Job.committed_at < limit).all():
            job.status = JobStatus.TIMEOUT
            job.failure_reason = "buyer did not send data in time"
            task = db.get(Task, job.task_id)
            if task is not None and task.status == constants.TASK_ASSIGNED:
                task.status = constants.TASK_OPEN if task.expires_at > now else constants.TASK_EXPIRED
            counts["commit_timeouts"] += 1
            events.append(_event(constants.EVENT_JOB_TIMEOUT, job, "No data received before the commitment deadline"))

        # Seller acknowledged receipt but never delivered: slash.
        limit = now - timedelta(seconds=constants.JOB_DELIVERY_TIMEOUT_SECONDS)
        for job in db.query(Job).filter(Job.status == JobStatus.DATA_SENT, Job.received_at < limit).all():
            job.status = JobStatus.TIMEOUT
            job.failure_reason = "seller did not deliver in time"
            seller = db.get(Seller, job.seller_id)
            slashed = slash_stake(db, seller, constants.SLASH_TIMEOUT_PERCENT, "delivery timeout", job.job_id) if seller else 0
            counts["delivery_timeouts"] += 1
            events.append(_event(constants.EVENT_STAKE_SLASHED, job, f"Delivery timeout: slashed {constants.SLASH_TIMEOUT_PERCENT}%", slashed))

        # Delivered but never paid: the invoice expires, buyer gets nothing.
        limit = now - timedelta(seconds=constants.PAYMENT_TIMEOUT_SECONDS)
        for job in db.query(Job).filter(Job.status == JobStatus.DELIVERED, Job.payment_verified.is_(False),
                                        Job.delivered_at < limit).all():
            job.status = JobStatus.TIMEOUT
            job.failure_reason = "buyer did not pay the invoice in time"
            counts["unpaid"] += 1
            events.append(_event(constants.EVENT_JOB_TIMEOUT, job, "Invoice unpaid before deadline"))

        # Paid but the buyer never called settle: settle on their behalf.
        limit = now - timedelta(seconds=constants.AUTO_SETTLE_AFTER_SECONDS)
        for job in db.query(Job).filter(Job.status == JobStatus.DELIVERED, Job.payment_verified.is_(True),
                                        Job.paid_at < limit).all():
            fee = settle_job_row(db, job, db.get(Seller, job.seller_id), now)
            counts["auto_settled"] += 1
            events.append(_event(constants.EVENT_PAYMENT_SETTLED, job, f"Auto-settled after payment (fee {fee} sats)"))
    for e in events:
        broadcaster.publish(e)
    if any(counts.values()):
        logger.info("Sweeper: %s", counts)
    return counts


def run_sweeper_safe() -> None:
    try:
        run_sweeper()
    except Exception as e:  # noqa: BLE001
        logger.error("Sweeper error: %s", e)


__all__ = ["run_sweeper", "run_sweeper_safe", "settle_job_row"]
