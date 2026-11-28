"""Startup seeding: built-in sellers, optional demo history, feed replay."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from registry import database
from registry.auth import builtin_seller_key
from registry.lightning import calculate_platform_fee, new_id, recompute_reputation
from registry.models import Job, JobStatus, Seller, SellerStatus, Stake, Transaction, utcnow
from registry.sse import broadcaster
from shared import constants, schemas
from shared.crypto_utils import hash_token

logger = logging.getLogger(__name__)

BUILTINS = (
    ("sel_summarizer", "summarizer"),
    ("sel_classifier", "classifier"),
)


def _builtin_spec(seller_id: str) -> dict:
    if seller_id == "sel_summarizer":
        url = constants.seller_summarizer_url()
        return dict(capability=constants.SUMMARIZER_CAPABILITY, price=constants.SUMMARIZER_PRICE_PER_UNIT,
                    unit=constants.SUMMARIZER_UNIT, stake=constants.SUMMARIZER_STAKE, url=url,
                    image="sha256:" + "0" * 63 + "1")
    url = constants.seller_classifier_url()
    return dict(capability=constants.CLASSIFIER_CAPABILITY, price=constants.CLASSIFIER_PRICE_PER_UNIT,
                unit=constants.CLASSIFIER_UNIT, stake=constants.CLASSIFIER_STAKE, url=url,
                image="sha256:" + "0" * 63 + "2")


def seed_builtin_sellers() -> None:
    """Create the two built-in sellers, or refresh their URLs and keys.

    Status is only ever moved INACTIVE -> ACTIVE here (the health check will
    re-mark an unreachable seller). SUSPENDED sellers stay suspended, so a
    registry restart never undoes a slash.
    """
    with database.get_db() as db:
        for seller_id, _kind in BUILTINS:
            spec = _builtin_spec(seller_id)
            key = builtin_seller_key(seller_id)
            key_hash = hash_token(key) if key else None
            if key is None:
                logger.error("No MUHR_SELLER_KEY_%s set: built-in seller %s cannot authenticate", seller_id.upper(), seller_id)
            s = db.get(Seller, seller_id)
            if s is None:
                db.add(Seller(
                    seller_id=seller_id,
                    lightning_pubkey=f"builtin_{seller_id}_pubkey",
                    capability=spec["capability"],
                    price_sats_per_unit=spec["price"],
                    unit_definition=spec["unit"],
                    endpoint_url=spec["url"],
                    commitment_endpoint=f"{spec['url']}{constants.API_SELLER_COMMIT}",
                    docker_image_hash=spec["image"],
                    api_key_hash=key_hash,
                    stake_sats=spec["stake"],
                    stake_verified=False,
                    max_job_value=spec["stake"] // constants.STAKE_TO_MAX_JOB_RATIO,
                    reputation_score=50.0,
                    status=SellerStatus.ACTIVE,
                    registered_at=utcnow(),
                ))
                db.add(Stake(stake_id=f"stake_{seller_id}", seller_id=seller_id, amount_sats=spec["stake"],
                             payment_hash="builtin-unverified", status="active", created_at=utcnow()))
                logger.info("Seeded built-in seller %s", seller_id)
            else:
                s.endpoint_url = spec["url"]
                s.commitment_endpoint = f"{spec['url']}{constants.API_SELLER_COMMIT}"
                s.api_key_hash = key_hash
                if s.status == SellerStatus.INACTIVE:
                    s.status = SellerStatus.ACTIVE
                recompute_reputation(s)


def seed_demo_dataset() -> None:
    """Idempotent demo history (settled jobs + ledger rows), clearly labelled DEMO."""
    if not constants.env_flag("MUHR_SEED_DEMO_DATA", True):
        return
    with database.get_db() as db:
        if db.query(Job).filter(Job.task_id.like("task_seed_%")).first():
            return
        now = utcnow()
        scenarios = [
            ("task_seed_0001", "job_seed_0001", "sel_summarizer", constants.SUMMARIZER_CAPABILITY, 150, 1250),
            ("task_seed_0002", "job_seed_0002", "sel_summarizer", constants.SUMMARIZER_CAPABILITY, 200, 1310),
            ("task_seed_0003", "job_seed_0003", "sel_classifier", constants.CLASSIFIER_CAPABILITY, 80, 870),
            ("task_seed_0004", "job_seed_0004", "sel_classifier", constants.CLASSIFIER_CAPABILITY, 120, 910),
        ]
        t_base = now - timedelta(hours=50)
        for i, (task_id, job_id, seller_id, cap, budget, ms) in enumerate(scenarios):
            t0 = t_base + timedelta(hours=4 * i)
            t1, t2, t3 = t0 + timedelta(minutes=2), t0 + timedelta(minutes=5), t0 + timedelta(minutes=6)
            ph = hashlib.sha256(f"muhr-seed:{job_id}".encode()).hexdigest()
            db.add(Job(
                job_id=job_id, task_id=task_id, seller_id=seller_id, capability=cap,
                budget_sats=budget, accepted_price_sats=budget, payment_hash=ph,
                computation_hash=hashlib.sha256(f"commit:{job_id}".encode()).hexdigest(),
                result_hash=hashlib.sha256(f"result:{job_id}".encode()).hexdigest(),
                lightning_payment_hash=ph, lightning_mode="DEMO",
                payment_verified=True, payment_verified_by="seed",
                status=JobStatus.SETTLED, created_at=t0, committed_at=t1, received_at=t1,
                delivered_at=t2, paid_at=t3, settled_at=t3,
            ))
            db.add(Transaction(tx_id=new_id("tx"), job_id=job_id, seller_id=seller_id, type="payment",
                               amount_sats=budget, mode="DEMO", timestamp=t3))
            fee = calculate_platform_fee(budget)
            db.add(Transaction(tx_id=new_id("tx"), job_id=job_id, seller_id=seller_id, type="platform_fee",
                               amount_sats=fee, timestamp=t3))
            s = db.get(Seller, seller_id)
            if s:
                s.jobs_completed += 1
                s.avg_response_ms = ms
                recompute_reputation(s)
    logger.info("Seeded demo jobs/transactions (task_seed_*)")


def _synthetic_events_for_job(job: Job) -> list[schemas.FeedEvent]:
    t0 = job.created_at or utcnow()
    t_commit = job.committed_at or (t0 + timedelta(seconds=1))
    t_del = job.delivered_at or t_commit
    t_set = job.settled_at or t_del
    base = dict(job_id=job.job_id, task_id=job.task_id, seller_id=job.seller_id,
                capability=job.capability, amount_sats=job.budget_sats)
    evs = [
        schemas.FeedEvent(type=constants.EVENT_TASK_POSTED, timestamp=t0, task_id=job.task_id,
                          capability=job.capability, amount_sats=job.budget_sats,
                          detail=f"Task posted: {job.task_id} ({job.capability})"),
        schemas.FeedEvent(type=constants.EVENT_COMMITMENT, timestamp=t_commit, detail=f"Seller {job.seller_id} committed", **base),
        schemas.FeedEvent(type=constants.EVENT_DATA_SENT, timestamp=t_commit + timedelta(seconds=1),
                          detail=f"Sealed input received by {job.seller_id}", **base),
        schemas.FeedEvent(type=constants.EVENT_RESULT_DELIVERED, timestamp=t_del, detail=f"Encrypted result delivered for {job.job_id}", **base),
        schemas.FeedEvent(type=constants.EVENT_HTLC_OPENED, timestamp=t_del, detail=f"Invoice issued, locked to {job.payment_hash[:16]}…",
                          lightning_payment_hash=job.payment_hash, lightning_mode=job.lightning_mode, **base),
    ]
    if job.status == JobStatus.SETTLED:
        evs += [
            schemas.FeedEvent(type=constants.EVENT_LIGHTNING_PAID, timestamp=t_set, detail=f"Lightning {job.lightning_mode or 'DEMO'} payment verified",
                              lightning_payment_hash=job.lightning_payment_hash, lightning_mode=job.lightning_mode, **base),
            schemas.FeedEvent(type=constants.EVENT_PAYMENT_SETTLED, timestamp=t_set,
                              detail=f"Settled (platform fee {calculate_platform_fee(job.budget_sats)} sats) for {job.job_id}",
                              lightning_payment_hash=job.lightning_payment_hash, lightning_mode=job.lightning_mode, **base),
        ]
    return evs


def rebuild_seed_feed_from_db() -> None:
    with database.get_db() as db:
        jobs = db.query(Job).filter(Job.task_id.like("task_seed_%")).order_by(Job.created_at.asc()).all()
        events = [e for j in jobs for e in _synthetic_events_for_job(j)]
    events.sort(key=lambda e: e.timestamp)
    broadcaster.extend_history(events)


def bootstrap() -> None:
    """Idempotent startup sequence (also called by tests)."""
    database.init_db()
    seed_builtin_sellers()
    seed_demo_dataset()
    if not broadcaster.history:
        rebuild_seed_feed_from_db()
    if constants.env_flag("MUHR_SEED_DEMO_APPROVAL", constants.demo_mode()):
        _seed_demo_approval()


def _seed_demo_approval() -> None:
    from registry.models import Approval
    with database.get_db() as db:
        if db.get(Approval, "req_demo_001") is None:
            db.add(Approval(request_id="req_demo_001",
                            reason="Model upgrade: higher token cap for a long document run.",
                            amount_sats=50,
                            task_description="Re-summarize the uploaded brief with 8k output tokens.",
                            status="pending", created_at=utcnow()))
