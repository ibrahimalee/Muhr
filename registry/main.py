"""MUHR Registry - FastAPI backend for the AI agent marketplace.

Protocol, one job:

1. buyer   POST /api/tasks                      -> task_id + buyer_token
2. buyer   POST seller/commit                    seller POST /api/jobs/{task}/commitment (seller key) -> job_id
3. buyer   POST seller/job (input sealed to the seller's X25519 key)
           seller POST /api/jobs/{job}/received, runs the job, encrypts the result under K,
           issues an invoice for the accepted price, POST /api/jobs/{job}/complete with
           sha256(result), sha256(K), sha256(ciphertext) and the invoice hash.
4. buyer   checks invoice amount + hash against the registry, pays, obtains K
           (K = HKDF(preimage) or seller releases K after its wallet sees the payment),
           decrypts and checks sha256(result).
5. buyer   POST /api/jobs/{job}/payment (proof) and /settle, or /dispute with evidence.

Deadlines are enforced by ``registry.sweeper``.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Always load the repo-root .env so starting the registry from any cwd works.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

import logging  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from datetime import timedelta  # noqa: E402
from typing import Optional  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import httpx  # noqa: E402
from fastapi import Body, Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from sqlalchemy import func, update  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from registry import auth, database  # noqa: E402
from registry.health import health_check_all_sellers_sync  # noqa: E402
from registry.lightning import calculate_platform_fee, new_id, recompute_reputation, slash_stake, update_response_time  # noqa: E402
from registry.models import Approval, Job, JobStatus, Seller, SellerStatus, Stake, Task, Transaction, utcnow  # noqa: E402
from registry.seed import bootstrap  # noqa: E402
from registry.sse import broadcaster  # noqa: E402
from registry.sweeper import run_sweeper_safe, settle_job_row  # noqa: E402
from shared import bolt11, constants, crypto_utils, schemas  # noqa: E402
from shared.crypto_utils import hash_token, new_token  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_scheduler = None
KEY_RELEASE_MODES = {constants.KEY_RELEASE_PREIMAGE, constants.KEY_RELEASE_SELLER_CONFIRMED}
OPEN_JOB_STATES = [JobStatus.COMMITTED, JobStatus.DATA_SENT, JobStatus.DELIVERED]


# ============================================================================
# Helpers
# ============================================================================

def emit(type_: str, *, job: Job | None = None, detail: str, amount: int | None = None, **extra) -> None:
    fields = dict(job_id=job.job_id, task_id=job.task_id, seller_id=job.seller_id,
                  capability=job.capability, amount_sats=job.accepted_price_sats or job.budget_sats) if job else {}
    if amount is not None:
        fields["amount_sats"] = amount
    fields.update(extra)
    broadcaster.publish(schemas.FeedEvent(type=type_, timestamp=utcnow(), detail=detail, **fields))


def _is_local_or_private_host(host: str) -> bool:
    h = (host or "").strip().lower().strip("[]")
    if not h or h in {"localhost", "::1"} or h.endswith(".local") or h.endswith(".localhost"):
        return True
    if re.match(r"^(127|10)\.\d{1,3}\.\d{1,3}\.\d{1,3}$", h) or re.match(r"^192\.168\.\d{1,3}\.\d{1,3}$", h):
        return True
    if re.match(r"^169\.254\.", h) or h == "0.0.0.0":
        return True
    m = re.match(r"^172\.(\d{1,3})\.\d{1,3}\.\d{1,3}$", h)
    return bool(m and 16 <= int(m.group(1)) <= 31)


def _validate_public_http_url(value: str, *, field_name: str) -> None:
    p = urlparse(value)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an absolute http(s) URL")
    if not constants.demo_mode() and _is_local_or_private_host(p.hostname or ""):
        raise HTTPException(status_code=400, detail=f"{field_name} must be publicly reachable (not localhost/private)")


def _get_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_seller(request: Request, db: Session, job: Job, claimed_seller_id: str | None = None) -> Seller:
    """Authenticate as the seller *assigned to this job*; a key for another seller never works."""
    if claimed_seller_id is not None and claimed_seller_id != job.seller_id:
        raise HTTPException(status_code=403, detail="seller_id does not match the seller assigned to this job")
    return auth.require_seller(request, db.get(Seller, job.seller_id))


def _job_buyer(request: Request, db: Session, job: Job) -> Task:
    return auth.require_buyer(request, db.get(Task, job.task_id))


def _summary(j: Job) -> schemas.JobSummary:
    return schemas.JobSummary(
        job_id=j.job_id, task_id=j.task_id, seller_id=j.seller_id, capability=j.capability,
        budget_sats=j.budget_sats, accepted_price_sats=j.accepted_price_sats, status=j.status.value,
        payment_hash=j.payment_hash or "", computation_hash=j.computation_hash, result_hash=j.result_hash,
        key_commitment=j.key_commitment, ciphertext_hash=j.ciphertext_hash, key_release=j.key_release, bolt11=j.bolt11,
        lightning_payment_hash=j.lightning_payment_hash, lightning_mode=j.lightning_mode,
        payment_verified=bool(j.payment_verified), created_at=j.created_at, committed_at=j.committed_at,
        delivered_at=j.delivered_at, settled_at=j.settled_at,
    )


def _reopen_task(db: Session, task_id: str) -> None:
    task = db.get(Task, task_id)
    if task is not None and task.status == constants.TASK_ASSIGNED:
        task.status = constants.TASK_OPEN if task.expires_at > utcnow() else constants.TASK_EXPIRED


def _payment_tx_id(db: Session, job_id: str) -> Optional[str]:
    tx = db.query(Transaction).filter(Transaction.job_id == job_id, Transaction.type == "payment").first()
    return tx.tx_id if tx else None


def _mark_paid(db: Session, job: Job, verified_by: str) -> tuple[str, bool]:
    """Record a verified payment exactly once. Returns (tx_id, newly_recorded)."""
    if job.payment_verified:
        return _payment_tx_id(db, job.job_id) or "", False
    job.payment_verified = True
    job.payment_verified_by = verified_by
    job.paid_at = utcnow()
    job.lightning_payment_hash = job.payment_hash
    tx_id = new_id("tx")
    db.add(Transaction(tx_id=tx_id, job_id=job.job_id, seller_id=job.seller_id, type="payment",
                       amount_sats=job.accepted_price_sats or job.budget_sats,
                       mode=job.lightning_mode or "DEMO", timestamp=utcnow()))
    return tx_id, True


# ============================================================================
# App
# ============================================================================

def _start_scheduler() -> None:
    global _scheduler
    if constants.env_flag("MUHR_DISABLE_HEALTH_SCHEDULER", False):
        logger.info("Background scheduler disabled via MUHR_DISABLE_HEALTH_SCHEDULER")
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(health_check_all_sellers_sync, "interval", seconds=constants.HEALTH_CHECK_INTERVAL_SECONDS, id="health")
    _scheduler.add_job(run_sweeper_safe, "interval", seconds=constants.SWEEPER_INTERVAL_SECONDS, id="sweeper")
    _scheduler.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MUHR Registry (demo_mode=%s)", constants.demo_mode())
    bootstrap()
    _start_scheduler()
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="MUHR Registry", description="AI Agent Marketplace on Lightning Network",
              version="2.0.0", lifespan=lifespan)


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("MUHR_CORS_ALLOW_ORIGINS", "").strip()
    if raw == "*":
        return ["*"]
    if not raw:
        return [f"http://{h}:{p}" for h in ("localhost", "127.0.0.1") for p in (3000, 3001, 5173, 8080)]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(CORSMiddleware, allow_origins=_parse_allowed_origins(), allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request IDs + rate limits. Returns a response (never raises) so CORS still applies."""
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        rule = auth.RATE_LIMITS.get(request.url.path)
        if rule:
            bucket, env_name, default = rule
            per_min = int(os.getenv(env_name, str(default)))
            if not auth.limiter.allow(bucket, auth.client_ip(request), per_min):
                return JSONResponse(status_code=429, content={"detail": f"Rate limit exceeded ({bucket})"},
                                    headers={"X-Request-ID": request_id})
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Never leak SQL or stack traces to clients."""
    rid = getattr(request.state, "request_id", "-")
    logger.exception("Unhandled error on %s %s (request %s)", request.method, request.url.path, rid)
    return JSONResponse(status_code=500, content={"detail": f"Internal error (request {rid})"})


@app.get("/")
def root():
    return {"service": "MUHR Registry", "status": "running", "version": app.version, "demo_mode": constants.demo_mode()}


@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": schemas._iso_utc(utcnow())}


# ============================================================================
# Sellers
# ============================================================================

@app.post(constants.API_SELLERS_REGISTER, response_model=schemas.SellerRegisterResponse)
def register_seller(request: schemas.SellerRegisterRequest, db: Session = Depends(database.get_db_session)):
    demo = constants.demo_mode()
    _validate_public_http_url(request.endpoint_url, field_name="endpoint_url")
    _validate_public_http_url(request.commitment_endpoint, field_name="commitment_endpoint")
    if not demo and not request.commitment_endpoint.startswith(request.endpoint_url.rstrip("/") + "/"):
        raise HTTPException(status_code=400, detail="commitment_endpoint must be under endpoint_url")
    if not demo:
        if not re.fullmatch(r"0[23][0-9a-fA-F]{64}", request.lightning_pubkey):
            raise HTTPException(status_code=400, detail="lightning_pubkey must be a 33-byte compressed node pubkey (66 hex)")
        if not constants.env_flag("MUHR_ALLOW_UNVERIFIED_SELLERS", False):
            verified = {h.strip() for h in os.getenv("MUHR_VERIFIED_DOCKER_IMAGE_HASHES", "").split(",") if h.strip()}
            if request.docker_image_hash not in verified:
                raise HTTPException(status_code=403, detail="Seller docker image not verified for registration on this registry")
    if db.query(Seller).filter(Seller.lightning_pubkey == request.lightning_pubkey).first():
        raise HTTPException(status_code=409, detail="A seller with this lightning_pubkey is already registered")

    # Stake is never invented outside DEMO: real sellers start at 0 until an operator
    # credits a verified deposit (POST /stake with the admin key).
    if demo or constants.env_flag("MUHR_ALLOW_UNVERIFIED_STAKE", False):
        stake_sats = constants.DEFAULT_DEMO_STAKE_SATS
    else:
        stake_sats = 0

    seller_id = f"sel_{uuid.uuid4().hex[:8]}"
    seller_key = new_token("hsk")
    now = utcnow()
    seller = Seller(
        seller_id=seller_id, lightning_pubkey=request.lightning_pubkey, capability=request.capability,
        price_sats_per_unit=request.price_sats_per_unit, unit_definition=request.unit_definition,
        endpoint_url=request.endpoint_url.rstrip("/"), commitment_endpoint=request.commitment_endpoint,
        docker_image_hash=request.docker_image_hash, api_key_hash=hash_token(seller_key),
        stake_sats=stake_sats, stake_verified=False,
        max_job_value=stake_sats // constants.STAKE_TO_MAX_JOB_RATIO,
        reputation_score=50.0, status=SellerStatus.ACTIVE, registered_at=now,
    )
    db.add(seller)
    if stake_sats:
        db.add(Stake(stake_id=new_id("stake"), seller_id=seller_id, amount_sats=stake_sats,
                     payment_hash=(request.stake_payment_hash or "unverified")[:64], status="active", created_at=now))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Seller already registered")
    logger.info("Seller registered: %s (%s)", seller_id, request.capability)
    return schemas.SellerRegisterResponse(
        seller_id=seller_id, status=seller.status.value, stake_sats=stake_sats, stake_verified=False,
        max_job_value=seller.max_job_value, registered_at=now, seller_key=seller_key,
    )


@app.post(constants.API_SELLER_STAKE, response_model=schemas.StakeDepositResponse)
def deposit_stake(seller_id: str, body: schemas.StakeDepositRequest, request: Request,
                  db: Session = Depends(database.get_db_session)):
    """Credit stake. Outside DEMO this is operator-only: the operator verifies the deposit
    payment out of band (the registry has no wallet) and then credits it."""
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    if constants.demo_mode():
        auth.require_seller(request, seller)
    else:
        auth.require_admin(request)
        seller.stake_verified = True
    seller.stake_sats += body.amount_sats
    seller.max_job_value = seller.stake_sats // constants.STAKE_TO_MAX_JOB_RATIO
    if seller.status == SellerStatus.SUSPENDED and seller.stake_sats >= constants.MIN_STAKE_SATS:
        seller.status = SellerStatus.ACTIVE
    stake_id = new_id("stake")
    db.add(Stake(stake_id=stake_id, seller_id=seller_id, amount_sats=body.amount_sats,
                 payment_hash=body.payment_hash.lower(), status="active", created_at=utcnow()))
    db.add(Transaction(tx_id=new_id("tx"), seller_id=seller_id, type="stake_deposit",
                       amount_sats=body.amount_sats, timestamp=utcnow()))
    db.commit()
    emit(constants.EVENT_STAKE_DEPOSITED, detail=f"Stake deposit +{body.amount_sats} sats (now {seller.stake_sats})",
         seller_id=seller_id, amount=body.amount_sats)
    return schemas.StakeDepositResponse(seller_id=seller_id, new_stake_sats=seller.stake_sats,
                                        new_max_job_value=seller.max_job_value, stake_id=stake_id,
                                        status=seller.status.value)


@app.post(constants.API_SELLER_UNSTAKE, response_model=schemas.StakeWithdrawResponse)
def withdraw_stake(seller_id: str, body: schemas.StakeWithdrawRequest, request: Request,
                   db: Session = Depends(database.get_db_session)):
    seller = auth.require_seller(request, db.get(Seller, seller_id))
    open_jobs = db.query(Job).filter(Job.seller_id == seller_id, Job.status.in_(OPEN_JOB_STATES)).count()
    if open_jobs:
        raise HTTPException(status_code=409, detail=f"Cannot withdraw stake with {open_jobs} open job(s)")
    amount = int(seller.stake_sats)
    seller.stake_sats = 0
    seller.max_job_value = 0
    seller.status = SellerStatus.SUSPENDED
    for st in db.query(Stake).filter(Stake.seller_id == seller_id, Stake.status == "active").all():
        st.status = "withdrawn"
    db.add(Transaction(tx_id=new_id("tx"), seller_id=seller_id, type="stake_withdrawal",
                       amount_sats=-amount, timestamp=utcnow()))
    db.commit()
    emit(constants.EVENT_STAKE_WITHDRAWN, detail=body.reason or f"Seller {seller_id} withdrew {amount} sats",
         seller_id=seller_id, amount=amount)
    return schemas.StakeWithdrawResponse(seller_id=seller_id, withdrawn_sats=amount, new_status=seller.status.value)


@app.get(constants.API_SELLERS, response_model=schemas.SellerListResponse)
def get_sellers(capability: Optional[str] = None, max_price: Optional[int] = None, min_jobs: Optional[int] = None,
                db: Session = Depends(database.get_db_session)):
    """Active, sufficiently staked sellers ordered by reputation (success rate), then price."""
    q = db.query(Seller).filter(Seller.status == SellerStatus.ACTIVE, Seller.stake_sats >= constants.MIN_STAKE_SATS)
    if capability:
        q = q.filter(Seller.capability == capability)
    if max_price is not None:
        q = q.filter(Seller.price_sats_per_unit <= max_price)
    if min_jobs is not None:
        q = q.filter(Seller.jobs_completed >= min_jobs)
    sellers = q.order_by(Seller.reputation_score.desc(), Seller.price_sats_per_unit.asc()).all()
    infos = [schemas.SellerInfo(
        seller_id=s.seller_id, capability=s.capability, price_sats_per_unit=s.price_sats_per_unit,
        unit_definition=s.unit_definition, jobs_completed=s.jobs_completed, jobs_failed=s.jobs_failed or 0,
        stake_sats=s.stake_sats, reputation_score=s.reputation_score, avg_response_ms=s.avg_response_ms,
        endpoint_url=s.endpoint_url, status=s.status.value, last_seen=s.last_seen,
    ) for s in sellers]
    return schemas.SellerListResponse(sellers=infos, total=len(infos), generated_at=utcnow())


# ============================================================================
# Tasks and jobs
# ============================================================================

@app.post(constants.API_TASKS, response_model=schemas.TaskPostResponse)
def post_task(request: schemas.TaskPostRequest, db: Session = Depends(database.get_db_session)):
    task_id = request.task_id or f"task_{uuid.uuid4().hex[:12]}"
    if db.get(Task, task_id) is not None:
        raise HTTPException(status_code=409, detail="Task already posted")
    buyer_token = new_token("hbt")
    now = utcnow()
    task = Task(task_id=task_id, capability=request.capability_needed, budget_sats=request.budget_sats,
                input_schema=request.input_schema, buyer_pubkey=request.buyer_pubkey,
                buyer_token_hash=hash_token(buyer_token), status=constants.TASK_OPEN, created_at=now,
                expires_at=now + timedelta(seconds=request.expiry_seconds))
    db.add(task)
    matched = db.query(Seller).filter(
        Seller.capability == request.capability_needed, Seller.status == SellerStatus.ACTIVE,
        Seller.stake_sats >= constants.MIN_STAKE_SATS, Seller.max_job_value >= 1,
    ).order_by(Seller.reputation_score.desc()).all()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task already posted")
    emit(constants.EVENT_TASK_POSTED, detail=f"Task posted for {request.capability_needed}", task_id=task_id,
         capability=request.capability_needed, amount=request.budget_sats)
    return schemas.TaskPostResponse(task_id=task_id, status=constants.TASK_OPEN,
                                    matched_sellers=[s.seller_id for s in matched],
                                    expires_at=task.expires_at, buyer_token=buyer_token)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(database.get_db_session)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": t.task_id, "capability": t.capability, "budget_sats": t.budget_sats, "status": t.status,
            "created_at": schemas._iso_utc(t.created_at), "expires_at": schemas._iso_utc(t.expires_at)}


@app.post("/api/jobs/{task_id}/commitment", response_model=schemas.CommitmentResponse)
def commit_to_job(task_id: str, body: schemas.CommitmentRequest, request: Request,
                  db: Session = Depends(database.get_db_session)):
    """Called by the *seller* (seller key). Creates exactly one job per task."""
    seller = auth.require_seller(request, db.get(Seller, body.seller_id))
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    now = utcnow()
    if task.expires_at <= now:
        raise HTTPException(status_code=410, detail="Task has expired")
    if task.capability != seller.capability:
        raise HTTPException(status_code=400, detail=f"Seller capability {seller.capability!r} does not match task {task.capability!r}")
    if seller.status != SellerStatus.ACTIVE or seller.stake_sats < constants.MIN_STAKE_SATS:
        raise HTTPException(status_code=400, detail="Seller is not active or is under-staked")
    if body.accepted_price_sats > task.budget_sats:
        raise HTTPException(status_code=400, detail="accepted_price_sats exceeds the task budget")
    if body.accepted_price_sats > seller.max_job_value:
        raise HTTPException(status_code=400, detail=f"Seller max_job_value ({seller.max_job_value}) < accepted_price ({body.accepted_price_sats})")

    # Atomic claim: only one seller can move the task from open -> assigned.
    claimed = db.execute(update(Task).where(Task.task_id == task_id, Task.status == constants.TASK_OPEN)
                         .values(status=constants.TASK_ASSIGNED)).rowcount
    if not claimed:
        raise HTTPException(status_code=409, detail=f"Task is not open (status={task.status})")
    job = Job(job_id=f"job_{uuid.uuid4().hex[:12]}", task_id=task_id, seller_id=seller.seller_id,
              capability=task.capability, budget_sats=task.budget_sats,
              accepted_price_sats=body.accepted_price_sats, payment_hash="",
              computation_hash=body.computation_hash.lower(), status=JobStatus.COMMITTED,
              created_at=now, committed_at=now)
    db.add(job)
    db.commit()
    emit(constants.EVENT_COMMITMENT, job=job, detail=f"Seller {seller.seller_id} committed at {body.accepted_price_sats} sats")
    return schemas.CommitmentResponse(commitment_accepted=True, job_id=job.job_id, data_can_be_sent=True)


@app.get("/api/jobs/{job_id}", response_model=schemas.JobSummary)
def get_job(job_id: str, db: Session = Depends(database.get_db_session)):
    return _summary(_get_job(db, job_id))


@app.post("/api/jobs/{job_id}/received")
def mark_received(job_id: str, body: schemas.JobReceivedRequest, request: Request,
                  db: Session = Depends(database.get_db_session)):
    """Seller acknowledges receipt of the sealed input. Starts the delivery deadline.

    The *seller* reports this (not the buyer) so a buyer cannot claim data was sent
    and get an honest seller slashed for a timeout."""
    job = _get_job(db, job_id)
    _job_seller(request, db, job, body.seller_id)
    if job.status == JobStatus.DATA_SENT:
        return {"status": "ok", "job_id": job_id}
    if job.status != JobStatus.COMMITTED:
        raise HTTPException(status_code=409, detail=f"Job must be committed, got {job.status.value}")
    job.status = JobStatus.DATA_SENT
    job.received_at = utcnow()
    db.commit()
    emit(constants.EVENT_DATA_SENT, job=job, detail=f"Sealed input received by {job.seller_id}")
    return {"status": "ok", "job_id": job_id}


@app.post("/api/jobs/{job_id}/complete", response_model=schemas.JobCompleteResponse)
def complete_job(job_id: str, body: schemas.JobCompleteRequest, request: Request,
                 db: Session = Depends(database.get_db_session)):
    job = _get_job(db, job_id)
    seller = _job_seller(request, db, job, body.seller_id)
    if job.status != JobStatus.DATA_SENT:
        raise HTTPException(status_code=409, detail=f"Job status must be data_sent, got {job.status.value}")
    if body.key_release not in KEY_RELEASE_MODES:
        raise HTTPException(status_code=400, detail=f"key_release must be one of {sorted(KEY_RELEASE_MODES)}")
    if body.amount_sats != job.accepted_price_sats:
        raise HTTPException(status_code=400, detail=f"Invoice amount {body.amount_sats} != accepted price {job.accepted_price_sats}")
    mode = body.lightning_mode.upper()
    try:
        inv = bolt11.decode(body.bolt11)
    except bolt11.InvoiceError as e:
        raise HTTPException(status_code=400, detail=f"Invalid invoice: {e}")
    if inv.demo and (mode != "DEMO" or not constants.demo_mode()):
        raise HTTPException(status_code=400, detail="Demo invoices are only accepted in DEMO mode")
    if not inv.demo and mode != "REAL":
        raise HTTPException(status_code=400, detail="A real BOLT-11 invoice must be reported with lightning_mode=REAL")
    if inv.payment_hash != body.invoice_payment_hash.lower():
        raise HTTPException(status_code=400, detail="invoice_payment_hash does not match the invoice")
    if inv.amount_sat != body.amount_sats:
        raise HTTPException(status_code=400, detail="Invoice amount does not match amount_sats")

    now = utcnow()
    if body.seller_committed_hash and job.computation_hash and body.seller_committed_hash.lower() != job.computation_hash:
        reason = f"computation_hash mismatch: committed={job.computation_hash[:16]}…, runtime={body.seller_committed_hash[:16]}…"
        slashed = slash_stake(db, seller, constants.SLASH_CONTAINER_MISMATCH_PERCENT, reason, job.job_id)
        job.status = JobStatus.FAILED
        job.failure_reason = reason
        job.seller_committed_hash = body.seller_committed_hash.lower()
        job.delivered_at = now
        _reopen_task(db, job.task_id)
        db.commit()
        emit(constants.EVENT_STAKE_SLASHED, job=job, detail=f"Stake slashed 100%: {reason}", amount=slashed)
        return schemas.JobCompleteResponse(verified=False, payment_status="slashed", slashed=True, slash_reason=reason)

    job.result_hash = body.result_hash.lower()
    job.seller_committed_hash = (body.seller_committed_hash or "").lower() or None
    job.payment_hash = inv.payment_hash
    job.bolt11 = body.bolt11
    job.key_commitment = body.key_commitment.lower()
    job.ciphertext_hash = body.ciphertext_hash.lower()
    job.key_release = body.key_release
    job.lightning_mode = mode
    job.status = JobStatus.DELIVERED
    job.delivered_at = now
    if job.received_at:
        update_response_time(seller, int((now - job.received_at).total_seconds() * 1000))
    db.commit()
    emit(constants.EVENT_RESULT_DELIVERED, job=job, detail=f"Encrypted result delivered for {job_id}")
    emit(constants.EVENT_HTLC_OPENED, job=job, detail=f"Invoice issued ({mode}), payment locked to {inv.payment_hash[:16]}…",
         lightning_payment_hash=inv.payment_hash, lightning_mode=mode)
    return schemas.JobCompleteResponse(verified=True, payment_status="awaiting_payment")


@app.post("/api/jobs/{job_id}/fail")
def fail_job(job_id: str, body: schemas.JobFailRequest, request: Request, db: Session = Depends(database.get_db_session)):
    """Seller reports it cannot deliver (e.g. every LLM provider is down). No slash,
    but it counts against the seller's success rate and the task reopens."""
    job = _get_job(db, job_id)
    seller = _job_seller(request, db, job, body.seller_id)
    if job.status not in (JobStatus.COMMITTED, JobStatus.DATA_SENT):
        raise HTTPException(status_code=409, detail=f"Cannot fail a job in status {job.status.value}")
    job.status = JobStatus.FAILED
    job.failure_reason = body.reason[:500]
    seller.jobs_failed = (seller.jobs_failed or 0) + 1
    recompute_reputation(seller)
    _reopen_task(db, job.task_id)
    db.commit()
    emit(constants.EVENT_JOB_FAILED, job=job, detail=f"Seller reported failure: {body.reason[:120]}")
    return {"status": "failed", "job_id": job_id}


@app.post(constants.API_JOB_PAYMENT, response_model=schemas.JobPaymentResponse)
def record_job_payment(job_id: str, body: schemas.JobPaymentRequest, request: Request,
                       db: Session = Depends(database.get_db_session)):
    """Buyer reports the payment. Verified immediately when a valid preimage is supplied;
    otherwise it stays pending until the seller confirms receipt from its wallet."""
    job = _get_job(db, job_id)
    _job_buyer(request, db, job)
    if body.seller_id != job.seller_id:
        raise HTTPException(status_code=400, detail="seller_id does not match the job")
    if job.status not in (JobStatus.DELIVERED, JobStatus.SETTLED):
        raise HTTPException(status_code=409, detail=f"Job is not awaiting payment (status={job.status.value})")
    if body.lightning_payment_hash.lower() != job.payment_hash:
        raise HTTPException(status_code=400, detail="lightning_payment_hash is not this job's invoice hash")
    if body.amount_sats != job.accepted_price_sats:
        raise HTTPException(status_code=400, detail=f"amount_sats must equal the accepted price ({job.accepted_price_sats})")
    if body.mode.upper() != (job.lightning_mode or "DEMO"):
        raise HTTPException(status_code=400, detail=f"mode must be {job.lightning_mode} for this invoice")

    if body.lightning_preimage:
        if not crypto_utils.preimage_matches(body.lightning_preimage, job.payment_hash):
            raise HTTPException(status_code=400, detail="lightning_preimage does not hash to the invoice payment_hash")
        tx_id, new = _mark_paid(db, job, "preimage")
    elif job.payment_verified:
        tx_id, new = _payment_tx_id(db, job_id) or "", False
    else:
        db.commit()
        return schemas.JobPaymentResponse(recorded=True, tx_id="", mode=job.lightning_mode or "DEMO",
                                          verified=False, verified_by=None)
    db.commit()
    if new:
        emit(constants.EVENT_LIGHTNING_PAID, job=job,
             detail=f"Lightning {job.lightning_mode}: {job.accepted_price_sats} sats to {job.seller_id} (verified by preimage)",
             lightning_payment_hash=job.payment_hash, lightning_mode=job.lightning_mode)
    return schemas.JobPaymentResponse(recorded=True, tx_id=tx_id, mode=job.lightning_mode or "DEMO",
                                      verified=True, verified_by=job.payment_verified_by)


@app.post(constants.API_JOB_PAYMENT_CONFIRM, response_model=schemas.JobPaymentResponse)
def confirm_job_payment(job_id: str, body: schemas.PaymentConfirmRequest, request: Request,
                        db: Session = Depends(database.get_db_session)):
    """Seller confirms its wallet received the invoice (MDK exposes no preimage to the payer)."""
    job = _get_job(db, job_id)
    _job_seller(request, db, job, body.seller_id)
    if body.payment_hash.lower() != job.payment_hash:
        raise HTTPException(status_code=400, detail="payment_hash is not this job's invoice hash")
    if job.status not in (JobStatus.DELIVERED, JobStatus.SETTLED):
        raise HTTPException(status_code=409, detail=f"Job is not awaiting payment (status={job.status.value})")
    tx_id, new = _mark_paid(db, job, "seller_wallet")
    db.commit()
    if new:
        emit(constants.EVENT_LIGHTNING_PAID, job=job,
             detail=f"Lightning {job.lightning_mode}: {job.accepted_price_sats} sats received by {job.seller_id} (seller wallet)",
             lightning_payment_hash=job.payment_hash, lightning_mode=job.lightning_mode)
    return schemas.JobPaymentResponse(recorded=True, tx_id=tx_id, mode=job.lightning_mode or "DEMO",
                                      verified=True, verified_by=job.payment_verified_by)


@app.post(constants.API_JOB_SETTLE)
def settle_job(job_id: str, request: Request, db: Session = Depends(database.get_db_session)):
    """Buyer accepts the result. Requires a verified payment."""
    job = _get_job(db, job_id)
    _job_buyer(request, db, job)
    if job.status == JobStatus.SETTLED:
        return {"status": "settled", "job_id": job_id, "fee_sats": calculate_platform_fee(job.accepted_price_sats or 0),
                "lightning_payment_hash": job.lightning_payment_hash, "lightning_mode": job.lightning_mode}
    if job.status != JobStatus.DELIVERED:
        raise HTTPException(status_code=409, detail=f"Job must be delivered before settlement, got {job.status.value}")
    if not job.payment_verified:
        raise HTTPException(status_code=409, detail="Payment has not been verified for this job")
    seller = db.get(Seller, job.seller_id)
    fee = settle_job_row(db, job, seller, utcnow())
    db.commit()
    emit(constants.EVENT_PAYMENT_SETTLED, job=job, detail=f"Payment settled for {job_id} (platform fee {fee} sats accrued)",
         lightning_payment_hash=job.lightning_payment_hash, lightning_mode=job.lightning_mode)
    if seller is not None:
        emit(constants.EVENT_REPUTATION_UPDATED, detail=f"Seller {seller.seller_id} reputation {seller.reputation_score:.1f}",
             seller_id=seller.seller_id)
    return {"status": "settled", "job_id": job_id, "fee_sats": fee,
            "lightning_payment_hash": job.lightning_payment_hash, "lightning_mode": job.lightning_mode}


async def _fetch_seller_key(seller: Seller, job: Job) -> Optional[bytes]:
    from shared.http import async_client
    try:
        async with async_client(timeout=20.0) as client:
            r = await client.post(f"{seller.endpoint_url}{constants.API_SELLER_KEY}",
                                  json={"job_id": job.job_id, "payment_hash": job.payment_hash})
        if r.status_code != 200:
            return None
        return crypto_utils.b64d(r.json()["key_b64"])
    except Exception:  # noqa: BLE001
        return None


@app.post(constants.API_JOB_DISPUTE, response_model=schemas.DisputeResponse)
async def dispute_job(job_id: str, body: schemas.DisputeRequest, request: Request):
    """Buyer claims the delivered result does not match what the seller committed to.

    The registry can check this without trusting either side:
    - payment is proven (preimage, or seller-wallet confirmation);
    - the ciphertext is byte-for-byte the one the seller committed to (sha256 reported at
      /complete, before payment), so a buyer who knows K cannot forge evidence;
    - the key must hash to the committed key_commitment;
    - the decrypted bytes must hash to the committed result_hash.
    A seller fault slashes SLASH_WRONG_RESULT_PERCENT. This proves *integrity*, not quality.
    """
    db = database.SessionLocal()
    try:
        job = _get_job(db, job_id)
        _job_buyer(request, db, job)
        if job.status not in (JobStatus.DELIVERED, JobStatus.SETTLED):
            raise HTTPException(status_code=409, detail=f"Nothing to dispute (status={job.status.value})")
        seller = db.get(Seller, job.seller_id)
        digest = crypto_utils.ciphertext_digest(body.result_ciphertext_b64, body.result_nonce_b64, body.result_tag_b64)
        if not job.ciphertext_hash or digest != job.ciphertext_hash:
            return schemas.DisputeResponse(upheld=False, detail="Evidence is not the ciphertext the seller committed to")

        if body.preimage_hex:
            if not crypto_utils.preimage_matches(body.preimage_hex, job.payment_hash):
                raise HTTPException(status_code=400, detail="preimage does not match the invoice")
            paid = True
        else:
            paid = bool(job.payment_verified)
        if not paid:
            raise HTTPException(status_code=409, detail="Payment is not proven; pay the invoice first")

        if job.key_release == constants.KEY_RELEASE_PREIMAGE:
            if not body.preimage_hex:
                raise HTTPException(status_code=400, detail="preimage_hex is required for preimage key release")
            key = crypto_utils.derive_result_key(bytes.fromhex(body.preimage_hex), job.job_id)
        elif body.key_b64:
            key = crypto_utils.b64d(body.key_b64)
            if crypto_utils.key_commitment(key) != job.key_commitment:
                return schemas.DisputeResponse(upheld=False, detail="Supplied key is not the key the seller committed to")
        else:
            key = await _fetch_seller_key(seller, job) if seller else None
            if key is None:
                fault = "Seller confirmed payment but did not release the result key"
                return _uphold(db, job, seller, fault)

        if crypto_utils.key_commitment(key) != job.key_commitment:
            return _uphold(db, job, seller, "Seller's released key does not match its key commitment")
        try:
            plaintext = crypto_utils.decrypt_with_key(key, body.result_ciphertext_b64, body.result_nonce_b64,
                                                      body.result_tag_b64, aad=job.job_id.encode())
        except Exception:  # noqa: BLE001
            return _uphold(db, job, seller, "Committed ciphertext does not decrypt under the committed key")
        if crypto_utils.hash_result(plaintext) != job.result_hash:
            return _uphold(db, job, seller, "Decrypted result does not match the committed result_hash")
        return schemas.DisputeResponse(upheld=False, detail="Result matches the seller's commitments")
    finally:
        db.close()


def _uphold(db: Session, job: Job, seller: Optional[Seller], reason: str) -> schemas.DisputeResponse:
    slashed = slash_stake(db, seller, constants.SLASH_WRONG_RESULT_PERCENT, reason, job.job_id) if seller else 0
    job.status = JobStatus.FAILED
    job.failure_reason = f"dispute upheld: {reason}"
    db.commit()
    emit(constants.EVENT_DISPUTE, job=job, detail=f"Dispute upheld: {reason}")
    emit(constants.EVENT_STAKE_SLASHED, job=job, detail=f"Stake slashed {constants.SLASH_WRONG_RESULT_PERCENT}%: {reason}", amount=slashed)
    return schemas.DisputeResponse(upheld=True, detail=reason, slashed_sats=slashed)


# ============================================================================
# Feed, listings, stats
# ============================================================================

@app.get(constants.API_FEED)
async def get_feed():
    return StreamingResponse(broadcaster.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.get("/api/debug/feed")
def debug_feed_state():
    tail = list(broadcaster.history)[-20:]
    return {"queue_len": len(broadcaster.history), "subscribers": broadcaster.subscriber_count(),
            "last_events": tail}


@app.get(constants.API_JOBS, response_model=schemas.JobListResponse)
def list_jobs(limit: int = 100, db: Session = Depends(database.get_db_session)):
    lim = max(1, min(limit, 500))
    rows = db.query(Job).order_by(Job.created_at.desc()).limit(lim).all()
    return schemas.JobListResponse(jobs=[_summary(j) for j in rows], total=db.query(Job).count(), generated_at=utcnow())


@app.get(constants.API_BUYER_WALLET)
async def get_buyer_wallet():
    """Optional read-only proxy of a *co-located* buyer wallet (local demos only).

    Off by default: a public marketplace should not hold or expose a buyer's wallet.
    Enable with MUHR_EXPOSE_BUYER_WALLET=true.
    """
    import asyncio
    now = schemas._iso_utc(utcnow())
    unavailable = {"available": False, "mode": "DEMO", "balance_sats": 0, "network": None, "pubkey": None, "generated_at": now}
    if not constants.env_flag("MUHR_EXPOSE_BUYER_WALLET", False):
        return {**unavailable, "detail": "Buyer wallet proxy disabled (set MUHR_EXPOSE_BUYER_WALLET=true for local demos)"}
    try:
        from buyer_mcp.lightning import LightningWallet
        status = await asyncio.wait_for(LightningWallet().wallet_status(), timeout=6.0)
    except asyncio.TimeoutError:
        return {**unavailable, "detail": "MDK wallet probe timed out (>6s)"}
    except Exception as e:  # noqa: BLE001
        return {**unavailable, "detail": f"buyer wallet unavailable: {e.__class__.__name__}"}
    bal = status.get("balance_sats")
    data = status.get("data") if isinstance(status.get("data"), dict) else {}
    return {"available": status.get("mode") == "REAL" and bal is not None, "mode": status.get("mode", "DEMO"),
            "balance_sats": int(bal or 0), "network": data.get("network"), "pubkey": data.get("pubkey"),
            "detail": status.get("detail"), "generated_at": now}


@app.get("/api/stats", response_model=schemas.MarketStats)
def get_market_stats(db: Session = Depends(database.get_db_session)):
    def total(*conds) -> int:
        return int(db.query(func.coalesce(func.sum(Transaction.amount_sats), 0)).filter(*conds).scalar() or 0)

    payment_types = ["payment", "lightning_payment_demo"]  # second one: older rows
    gross = total(Transaction.type.in_(payment_types))
    real = total(Transaction.type == "payment", Transaction.mode == "REAL")
    fees = total(Transaction.type == "platform_fee")
    return schemas.MarketStats(
        settled_jobs=db.query(Job).filter(Job.status == JobStatus.SETTLED).count(),
        active_sellers=db.query(Seller).filter(Seller.status == SellerStatus.ACTIVE).count(),
        net_to_sellers_sats=gross - fees, platform_fees_sats=fees, gross_job_volume_sats=gross,
        real_volume_sats=real, demo_volume_sats=gross - real,
        transaction_count=db.query(Transaction).count(), demo_mode=constants.demo_mode(), generated_at=utcnow(),
    )


# ============================================================================
# Human approval
# ============================================================================

@app.get(constants.API_APPROVE)
def list_pending_approvals(db: Session = Depends(database.get_db_session)):
    rows = db.query(Approval).filter(Approval.status == "pending").order_by(Approval.created_at.asc()).all()
    return {"pending": [schemas.ApprovalRequest(request_id=a.request_id, reason=a.reason, amount_sats=a.amount_sats,
                                                task_description=a.task_description) for a in rows]}


@app.post(constants.API_APPROVE)
def approve_route(request: Request, body: dict = Body(...), db: Session = Depends(database.get_db_session)):
    """- Buyer: POST ApprovalRequest (creates a pending request).
    - Operator: POST ApprovalResponse {request_id, approved} with X-Muhr-Admin-Key."""
    if {"reason", "amount_sats", "task_description"} <= body.keys():
        req = schemas.ApprovalRequest(**body)
        if db.get(Approval, req.request_id) is not None:
            raise HTTPException(status_code=409, detail="Approval request already exists")
        db.add(Approval(request_id=req.request_id, reason=req.reason, amount_sats=req.amount_sats,
                        task_description=req.task_description, status="pending", created_at=utcnow()))
        db.commit()
        emit(constants.EVENT_APPROVAL_REQUESTED, detail=f"Approval requested: {req.reason}", amount=req.amount_sats)
        return {"status": "pending", "request_id": req.request_id}
    if {"request_id", "approved"} <= body.keys():
        auth.require_admin(request)
        decision = schemas.ApprovalResponse(**body)
        row = db.get(Approval, decision.request_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if row.status != "pending":
            raise HTTPException(status_code=409, detail=f"Already decided ({row.status})")
        row.status = "approved" if decision.approved else "rejected"
        row.decided_at = utcnow()
        db.commit()
        emit(constants.EVENT_APPROVAL_DECIDED, detail=f"Approval {row.status}: {row.request_id}")
        return {"status": "decided", "approved": decision.approved}
    raise HTTPException(status_code=422, detail="Invalid approval payload")


@app.get("/api/approve/{request_id}", response_model=schemas.ApprovalStatusResponse)
def get_approval_status(request_id: str, db: Session = Depends(database.get_db_session)):
    row = db.get(Approval, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return schemas.ApprovalStatusResponse(request_id=row.request_id, status=row.status,
                                          approved=None if row.status == "pending" else row.status == "approved")


# ============================================================================
# Live demo (registry acts as a DEMO buyer)
# ============================================================================

@app.post("/api/demo/run_e2e", response_model=schemas.DemoRunResponse)
async def run_demo_e2e(body: schemas.DemoRunRequest):
    """Run the full buyer flow against a seller so the dashboard can show real work.

    Uses a DEMO wallet only (the registry never spends real sats) and the configured
    MUHR_REGISTRY_INTERNAL_URL, never anything derived from request headers.
    """
    from buyer_mcp.budget import BudgetManager
    from buyer_mcp.flow import BuyerFlow, FlowError
    from buyer_mcp.lightning import LightningWallet
    from buyer_mcp.registry_client import RegistryClient

    text = body.input_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input_text must be non-empty")
    db = database.SessionLocal()
    try:
        seller = db.get(Seller, body.seller_id.strip() or "sel_summarizer")
        if seller is None or seller.status != SellerStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Seller not found or not active")
        capability = body.capability or seller.capability
        seller_id = seller.seller_id
    finally:
        db.close()

    flow = BuyerFlow(
        registry=RegistryClient(constants.registry_internal_url()),
        wallet=LightningWallet(demo_mode=True),
        budget=BudgetManager(daily_budget_sats=10**9, persist=False),
    )
    try:
        result = await flow.run(capability=capability, seller_id=seller_id, text=text,
                                budget_sats=body.budget_sats, buyer_pubkey="registry_demo_buyer")
    except FlowError as e:
        raise HTTPException(status_code=502, detail=f"Demo E2E failed: {e}")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=(
            f"Network connect failed during demo E2E (registry={constants.registry_internal_url()}, "
            f"seller={seller.endpoint_url}). Is the seller running? {e.__class__.__name__}"))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Demo E2E network error: {e.__class__.__name__}: {e}")
    return schemas.DemoRunResponse(
        ok=True, task_id=result.task_id, job_id=result.job_id, seller_id=seller_id, capability=capability,
        budget_sats=result.amount_sats, payment_hash=result.payment_hash, lightning_payment_hash=result.payment_hash,
        lightning_mode=result.mode, result_hash=result.result_hash, result_text=result.result_text,
        result_preview=result.result_text[:320],
    )


@app.get("/api/demo/health")
async def demo_health():
    from shared.http import async_client
    seller_url = constants.seller_summarizer_url()
    out: dict[str, object] = {"registry": "ok", "summarizer_url": seller_url, "summarizer_ok": False}
    try:
        async with async_client(timeout=3.0) as c:
            r = await c.get(f"{seller_url}/health")
        out["summarizer_ok"] = r.status_code == 200
        out["summarizer_status"] = r.status_code
    except Exception as e:  # noqa: BLE001
        out["detail"] = f"{e.__class__.__name__}: {e!s}"[:300]
    return out


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

