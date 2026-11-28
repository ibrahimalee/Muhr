"""MUHR seller app factory (summarizer and classifier share all protocol code).

Endpoints:
  GET  /health
  POST /commit     buyer -> seller: quote + commitment; the seller registers the job itself
  POST /job        sealed input in; encrypted result + invoice out (pay to decrypt)
  POST /key        release the result key once payment is proven
  POST /demo/pay   DEMO only: stands in for the Lightning network revealing the preimage
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

from sellers import _invoice, _l402, llm_client  # noqa: E402
from sellers.processing import MAX_TOKENS, EncryptedResult, ProcessingFailed, process_sealed  # noqa: E402
from shared import constants, crypto_utils, schemas  # noqa: E402
from shared.http import async_client  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class SellerConfig:
    kind: str                     # summarizer | classifier
    seller_id: str
    capability: str
    price_per_unit: int
    unit_size: int                # tokens (summarizer) or items (classifier) per priced unit


@dataclass
class JobState:
    task_id: str
    price_sats: int
    computation_hash: str
    input_schema: dict = field(default_factory=dict)
    payment_hash: Optional[str] = None
    key: Optional[bytes] = None
    key_release: Optional[str] = None
    preimage: Optional[bytes] = None
    demo_paid: bool = False
    confirmed: bool = False


@dataclass
class SellerState:
    priv_raw: bytes
    pub_b64: str
    jobs: dict[str, JobState] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _seller_key(seller_id: str) -> Optional[str]:
    for name in ("MUHR_SELLER_KEY", f"MUHR_SELLER_KEY_{seller_id.upper()}"):
        v = os.getenv(name, "").strip()
        if v:
            return v
    return f"dev-insecure-key-{seller_id}" if constants.demo_mode() else None


def _load_keypair() -> tuple[bytes, str]:
    raw = os.getenv("MUHR_SELLER_X25519_PRIVATE_B64", "").strip()
    if raw:
        priv = crypto_utils.b64d(raw)
        return priv, crypto_utils.x25519_public_from_private(priv)
    return crypto_utils.generate_x25519_keypair()


def quote(cfg: SellerConfig, input_schema: dict) -> int:
    if cfg.kind == "summarizer":
        tokens = max(1, int(input_schema.get("bytes", 4000)) // 4)
        units = math.ceil(tokens / cfg.unit_size)
    else:
        units = math.ceil(max(1, int(input_schema.get("items", 1))) / cfg.unit_size)
    return max(1, units * cfg.price_per_unit)


def computation_hash(cfg: SellerConfig, task_id: str, input_schema: dict, price: int) -> str:
    """Commitment to the pipeline the seller will run (image + provider chain + task terms)."""
    payload = {
        "seller": cfg.seller_id,
        "image": os.getenv("MUHR_SELLER_IMAGE_HASH", "unpinned"),
        "isolation": os.getenv("MUHR_SELLER_ISOLATION", "none"),
        "pipeline": llm_client.pipeline_config(cfg.kind, MAX_TOKENS[cfg.kind]),
        "task_id": task_id,
        "input_schema": input_schema,
        "price_sats": price,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def _registry_post(cfg: SellerConfig, path: str, body: dict) -> dict:
    key = _seller_key(cfg.seller_id)
    if not key:
        raise HTTPException(status_code=500, detail="Seller key not configured (MUHR_SELLER_KEY)")
    async with async_client(timeout=20.0) as client:
        r = await client.post(f"{constants.registry_base_url()}{path}", json=body,
                              headers={constants.HEADER_SELLER_KEY: key})
    if r.status_code >= 400:
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text
        raise HTTPException(status_code=502 if r.status_code >= 500 else r.status_code,
                            detail=f"Registry rejected {path}: {detail}")
    return r.json()


async def _run_isolated(cfg: SellerConfig, job_id: str, sealed: dict, key: bytes, state: SellerState) -> EncryptedResult:
    """Process inside `docker run --network=none` so the seller process never sees plaintext."""
    docker = shutil.which("docker")
    if not docker:
        raise ProcessingFailed("MUHR_SELLER_ISOLATION=docker but docker is not on PATH")
    image = os.getenv("MUHR_SELLER_WORKER_IMAGE", f"muhr/seller-{cfg.kind}:latest")
    args = [docker, "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "65534:65534",
            "--memory", "512m", "--cpus", "1.0", "-e", "MUHR_SELLER_X25519_PRIVATE_B64",
            image, "python", "-m", "sellers.worker"]
    env = {**os.environ, "MUHR_SELLER_X25519_PRIVATE_B64": crypto_utils.b64e(state.priv_raw)}
    payload = json.dumps({"job_id": job_id, "kind": cfg.kind, "sealed_input": sealed,
                          "result_key_b64": crypto_utils.b64e(key)}).encode()
    proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE, env=env)
    out, err = await asyncio.wait_for(proc.communicate(payload), timeout=120)
    if proc.returncode != 0:
        raise ProcessingFailed(f"isolated worker failed: {err.decode(errors='replace')[-300:]}")
    d = json.loads(out)
    return EncryptedResult(d["result_ciphertext_b64"], d["result_nonce_b64"], d["result_tag_b64"],
                           d["result_hash"], d["ciphertext_hash"], d.get("plaintext_len", 0))


def create_seller_app(cfg: SellerConfig) -> FastAPI:
    app = FastAPI(title=f"Muhr Seller — {cfg.kind}", version="2.0.0")
    priv, pub = _load_keypair()
    state = SellerState(priv_raw=priv, pub_b64=pub)
    app.state.seller = state
    app.state.config = cfg

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "service": cfg.kind, "seller_id": cfg.seller_id, "demo_mode": constants.demo_mode(),
                "pipeline": llm_client.pipeline_config(cfg.kind, MAX_TOKENS[cfg.kind])["pipeline"],
                "isolation": os.getenv("MUHR_SELLER_ISOLATION", "none")}

    @app.post(constants.API_SELLER_COMMIT, response_model=schemas.SellerCommitResponse)
    async def commit(req: schemas.SellerCommitRequest) -> schemas.SellerCommitResponse:
        price = quote(cfg, req.input_schema)
        if price > req.budget_sats:
            return schemas.SellerCommitResponse(computation_hash="", accepted=False, estimated_ms=0,
                                                price_sats=price, seller_id=cfg.seller_id)
        ch = computation_hash(cfg, req.task_id, req.input_schema, price)
        reg = await _registry_post(cfg, constants.API_JOB_COMMITMENT.format(task_id=req.task_id),
                                   {"seller_id": cfg.seller_id, "computation_hash": ch, "accepted_price_sats": price})
        job_id = reg["job_id"]
        with state.lock:
            state.jobs[job_id] = JobState(task_id=req.task_id, price_sats=price, computation_hash=ch,
                                           input_schema=dict(req.input_schema))
        return schemas.SellerCommitResponse(computation_hash=ch, accepted=True, estimated_ms=4000, job_id=job_id,
                                            price_sats=price, seller_id=cfg.seller_id, seller_pubkey_b64=state.pub_b64)

    @app.post(constants.API_SELLER_JOB, response_model=schemas.SellerJobResponse)
    async def job(req: schemas.SellerJobRequest) -> schemas.SellerJobResponse:
        with state.lock:
            js = state.jobs.get(req.job_id)
        if js is None:
            raise HTTPException(status_code=404, detail="Unknown job (commit first)")
        if js.payment_hash:
            raise HTTPException(status_code=409, detail="Job already processed")
        await _registry_post(cfg, constants.API_JOB_RECEIVED.format(job_id=req.job_id), {"seller_id": cfg.seller_id})

        try:
            invoice = await _invoice.create_invoice(js.price_sats, memo=f"muhr:{req.job_id}")
        except _invoice.InvoiceFailed as e:
            await _registry_post(cfg, constants.API_JOB_FAIL.format(job_id=req.job_id),
                                 {"seller_id": cfg.seller_id, "reason": f"invoice: {e}"[:500]})
            raise HTTPException(status_code=502, detail=f"Could not issue invoice: {e}")

        if invoice.preimage is not None:
            key, release = crypto_utils.derive_result_key(invoice.preimage, req.job_id), constants.KEY_RELEASE_PREIMAGE
        else:
            key, release = os.urandom(32), constants.KEY_RELEASE_SELLER_CONFIRMED

        sealed = req.sealed_input.model_dump()
        try:
            if os.getenv("MUHR_SELLER_ISOLATION", "none").lower() == "docker":
                enc = await _run_isolated(cfg, req.job_id, sealed, key, state)
            else:
                enc = await process_sealed(cfg.kind, req.job_id, state.priv_raw, sealed, key)
        except (ProcessingFailed, ValueError) as e:
            await _registry_post(cfg, constants.API_JOB_FAIL.format(job_id=req.job_id),
                                 {"seller_id": cfg.seller_id, "reason": str(e)[:500]})
            raise HTTPException(status_code=502 if isinstance(e, ProcessingFailed) else 400, detail=f"Job failed: {e}")

        with state.lock:
            js.payment_hash, js.key, js.key_release, js.preimage = invoice.payment_hash, key, release, invoice.preimage
        await _registry_post(cfg, constants.API_JOB_COMPLETE.format(job_id=req.job_id), {
            "seller_id": cfg.seller_id, "result_hash": enc.result_hash, "invoice_payment_hash": invoice.payment_hash,
            "bolt11": invoice.bolt11, "amount_sats": invoice.amount_sats, "key_commitment": crypto_utils.key_commitment(key),
            "ciphertext_hash": enc.ciphertext_hash, "key_release": release,
            # Recomputed from the *live* config: if the pipeline changed since /commit, this differs.
            "seller_committed_hash": computation_hash(cfg, js.task_id, js.input_schema, js.price_sats),
            "lightning_mode": invoice.mode,
        })
        return schemas.SellerJobResponse(
            job_id=req.job_id, result_ciphertext_b64=enc.result_ciphertext_b64, result_nonce_b64=enc.result_nonce_b64,
            result_tag_b64=enc.result_tag_b64, result_hash=enc.result_hash, key_commitment=crypto_utils.key_commitment(key),
            key_release=release, bolt11=invoice.bolt11, payment_hash=invoice.payment_hash,
            amount_sats=invoice.amount_sats, mode=invoice.mode,
            macaroon=_l402.issue_macaroon(job_id=req.job_id, amount_sats=invoice.amount_sats, payment_hash=invoice.payment_hash),
        )

    @app.post(constants.API_SELLER_KEY, response_model=schemas.SellerKeyResponse)
    async def release_key(req: schemas.SellerKeyRequest, request: Request) -> schemas.SellerKeyResponse:
        with state.lock:
            js = state.jobs.get(req.job_id)
        if js is None or js.key is None or js.payment_hash != req.payment_hash.lower():
            raise HTTPException(status_code=404, detail="No delivered result for this job/payment_hash")
        preimage = _l402.check_l402(request.headers.get("authorization"), job_id=req.job_id, payment_hash=js.payment_hash)
        if preimage is None and req.preimage_hex and crypto_utils.preimage_matches(req.preimage_hex, js.payment_hash):
            preimage = req.preimage_hex
        if preimage is not None:
            by = "preimage"
        elif constants.demo_mode() and js.demo_paid:
            by = "seller_wallet"
        elif not constants.demo_mode() and await _invoice.invoice_paid(js.payment_hash):
            by = "seller_wallet"
        else:
            raise HTTPException(status_code=402, detail="Invoice not paid yet",
                                headers={"WWW-Authenticate": f'L402 invoice_payment_hash="{js.payment_hash}"'})
        if not js.confirmed:
            await _registry_post(cfg, constants.API_JOB_PAYMENT_CONFIRM.format(job_id=req.job_id),
                                 {"seller_id": cfg.seller_id, "payment_hash": js.payment_hash})
            js.confirmed = True
        return schemas.SellerKeyResponse(job_id=req.job_id, key_b64=crypto_utils.b64e(js.key), payment_confirmed_by=by)

    @app.post(constants.API_SELLER_DEMO_PAY, response_model=schemas.DemoPayResponse)
    async def demo_pay(req: schemas.DemoPayRequest) -> schemas.DemoPayResponse:
        if not constants.demo_mode():
            raise HTTPException(status_code=404, detail="Not found")
        with state.lock:
            js = next((j for j in state.jobs.values() if j.payment_hash == req.payment_hash.lower()), None)
            if js is None or js.preimage is None:
                raise HTTPException(status_code=404, detail="Unknown demo invoice")
            if req.amount_sats != js.price_sats:
                raise HTTPException(status_code=400, detail="Amount does not match the invoice")
            js.demo_paid = True
        return schemas.DemoPayResponse(payment_hash=js.payment_hash, preimage_hex=js.preimage.hex())

    return app
