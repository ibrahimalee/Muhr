"""Regression tests: one per issue that was found and fixed."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest

from shared import bolt11, crypto_utils

SK = {"X-Muhr-Seller-Key": "dev-insecure-key-sel_summarizer"}
CK = {"X-Muhr-Seller-Key": "dev-insecure-key-sel_classifier"}


def _task(stack, cap="text_summarization", budget=50, expiry=300):
    r = stack.registry.post("/api/tasks", json={"capability_needed": cap, "budget_sats": budget,
                                                "buyer_pubkey": "pk", "expiry_seconds": expiry})
    assert r.status_code == 200, r.text
    return r.json()


def _commit(stack, task_id, seller="sel_summarizer", key=SK, price=10):
    return stack.registry.post(f"/api/jobs/{task_id}/commitment", headers=key,
                               json={"seller_id": seller, "computation_hash": "c" * 64, "accepted_price_sats": price})


def _delivered_job(stack, price=10):
    t = _task(stack)
    job_id = _commit(stack, t["task_id"], price=price).json()["job_id"]
    assert stack.registry.post(f"/api/jobs/{job_id}/received", headers=SK, json={"seller_id": "sel_summarizer"}).status_code == 200
    pre = crypto_utils.generate_preimage()
    ph = crypto_utils.compute_payment_hash(pre)
    r = stack.registry.post(f"/api/jobs/{job_id}/complete", headers=SK, json={
        "seller_id": "sel_summarizer", "result_hash": "d" * 64, "invoice_payment_hash": ph,
        "bolt11": bolt11.make_demo_invoice(price, ph), "amount_sats": price, "key_commitment": "e" * 64,
        "ciphertext_hash": "f" * 64, "key_release": "preimage", "lightning_mode": "DEMO"})
    assert r.status_code == 200, r.text
    return t, job_id, pre, ph


def _seller(stack, sid):
    return next(s for s in stack.registry.get("/api/sellers").json()["sellers"] if s["seller_id"] == sid)


# ---------------- B1 / B2: auth ----------------

def test_B1_cannot_slash_another_seller(stack):
    t = _task(stack)
    job_id = _commit(stack, t["task_id"]).json()["job_id"]
    stack.registry.post(f"/api/jobs/{job_id}/received", headers=SK, json={"seller_id": "sel_summarizer"})
    body = {"seller_id": "sel_classifier", "result_hash": "d" * 64, "invoice_payment_hash": "a" * 64,
            "bolt11": bolt11.make_demo_invoice(10, "a" * 64), "amount_sats": 10, "key_commitment": "e" * 64,
            "ciphertext_hash": "f" * 64, "key_release": "preimage", "seller_committed_hash": "9" * 64}
    assert stack.registry.post(f"/api/jobs/{job_id}/complete", headers=CK, json=body).status_code == 403
    assert stack.registry.post(f"/api/jobs/{job_id}/complete", json={**body, "seller_id": "sel_summarizer"}).status_code == 401
    assert _seller(stack, "sel_classifier")["stake_sats"] == 10_000


def test_B2_unstake_and_stake_require_seller_key(stack):
    assert stack.registry.post("/api/sellers/sel_summarizer/unstake", json={}).status_code == 401
    assert stack.registry.post("/api/sellers/sel_summarizer/unstake", headers=CK, json={}).status_code == 401
    assert stack.registry.post("/api/sellers/sel_summarizer/stake", json={"amount_sats": 5, "payment_hash": "a" * 64}).status_code == 401
    assert _seller(stack, "sel_summarizer")["stake_sats"] == 10_000


def test_unstake_blocked_with_open_jobs(stack):
    t = _task(stack)
    _commit(stack, t["task_id"])
    assert stack.registry.post("/api/sellers/sel_summarizer/unstake", headers=SK, json={}).status_code == 409


def test_buyer_endpoints_need_the_task_token(stack):
    t, job_id, pre, ph = _delivered_job(stack)
    pay = {"seller_id": "sel_summarizer", "amount_sats": 10, "mode": "DEMO", "lightning_payment_hash": ph,
           "lightning_preimage": pre.hex()}
    assert stack.registry.post(f"/api/jobs/{job_id}/payment", json=pay).status_code == 401
    assert stack.registry.post(f"/api/jobs/{job_id}/settle").status_code == 401
    other = _task(stack)
    assert stack.registry.post(f"/api/jobs/{job_id}/settle", headers={"X-Muhr-Buyer-Token": other["buyer_token"]}).status_code == 401


# ---------------- A8: state machine ----------------

def test_A8_capability_mismatch_rejected(stack):
    t = _task(stack)
    assert _commit(stack, t["task_id"], seller="sel_classifier", key=CK).status_code == 400


def test_A8_only_one_commit_per_task(stack):
    t = _task(stack)
    assert _commit(stack, t["task_id"]).status_code == 200
    assert _commit(stack, t["task_id"]).status_code == 409


def test_A8_price_above_budget_rejected_and_price_is_stored(stack):
    t = _task(stack, budget=50)
    assert _commit(stack, t["task_id"], price=51).status_code == 400
    job_id = _commit(stack, t["task_id"], price=7).json()["job_id"]
    assert stack.registry.get(f"/api/jobs/{job_id}").json()["accepted_price_sats"] == 7


def test_A8_expired_task_rejected(stack):
    t = _task(stack, expiry=10)
    from registry import database
    from registry.models import Task, utcnow
    with database.get_db() as db:
        db.get(Task, t["task_id"]).expires_at = utcnow() - timedelta(seconds=1)
    assert _commit(stack, t["task_id"]).status_code == 410


def test_A8_settle_requires_verified_payment(stack):
    t, job_id, pre, ph = _delivered_job(stack)
    hdr = {"X-Muhr-Buyer-Token": t["buyer_token"]}
    assert stack.registry.post(f"/api/jobs/{job_id}/settle", headers=hdr).status_code == 409


def test_A8_payment_is_verified_exactly_once(stack):
    t, job_id, pre, ph = _delivered_job(stack)
    hdr = {"X-Muhr-Buyer-Token": t["buyer_token"]}
    base = {"seller_id": "sel_summarizer", "mode": "DEMO", "lightning_payment_hash": ph}
    assert stack.registry.post(f"/api/jobs/{job_id}/payment", headers=hdr, json={**base, "amount_sats": 1_000_000,
                                                                               "lightning_preimage": pre.hex()}).status_code == 400
    assert stack.registry.post(f"/api/jobs/{job_id}/payment", headers=hdr, json={**base, "amount_sats": 10,
                                                                               "lightning_preimage": "00" * 32}).status_code == 400
    assert stack.registry.post(f"/api/jobs/{job_id}/payment", headers=hdr, json={**base, "amount_sats": 10, "mode": "REAL",
                                                                               "lightning_preimage": pre.hex()}).status_code == 400
    for _ in range(3):
        r = stack.registry.post(f"/api/jobs/{job_id}/payment", headers=hdr, json={**base, "amount_sats": 10,
                                                                                "lightning_preimage": pre.hex()})
        assert r.status_code == 200 and r.json()["verified"]
    assert stack.registry.get("/api/stats").json()["gross_job_volume_sats"] == 10
    assert stack.registry.post(f"/api/jobs/{job_id}/settle", headers=hdr).json()["status"] == "settled"


def test_A8_payment_on_undelivered_job_rejected(stack):
    t = _task(stack)
    job_id = _commit(stack, t["task_id"]).json()["job_id"]
    r = stack.registry.post(f"/api/jobs/{job_id}/payment", headers={"X-Muhr-Buyer-Token": t["buyer_token"]},
                            json={"seller_id": "sel_summarizer", "amount_sats": 10, "mode": "DEMO",
                                  "lightning_payment_hash": "a" * 64})
    assert r.status_code == 409


def test_complete_rejects_invoice_that_does_not_match(stack):
    t = _task(stack)
    job_id = _commit(stack, t["task_id"]).json()["job_id"]
    stack.registry.post(f"/api/jobs/{job_id}/received", headers=SK, json={"seller_id": "sel_summarizer"})
    body = {"seller_id": "sel_summarizer", "result_hash": "d" * 64, "invoice_payment_hash": "a" * 64,
            "bolt11": bolt11.make_demo_invoice(10, "b" * 64), "amount_sats": 10, "key_commitment": "e" * 64,
            "ciphertext_hash": "f" * 64, "key_release": "preimage"}
    assert stack.registry.post(f"/api/jobs/{job_id}/complete", headers=SK, json=body).status_code == 400
    body.update(bolt11=bolt11.make_demo_invoice(99, "a" * 64))
    assert stack.registry.post(f"/api/jobs/{job_id}/complete", headers=SK, json=body).status_code == 400


def test_H2_runtime_hash_mismatch_slashes_job_seller(stack):
    t = _task(stack)
    job_id = _commit(stack, t["task_id"]).json()["job_id"]
    stack.registry.post(f"/api/jobs/{job_id}/received", headers=SK, json={"seller_id": "sel_summarizer"})
    r = stack.registry.post(f"/api/jobs/{job_id}/complete", headers=SK, json={
        "seller_id": "sel_summarizer", "result_hash": "d" * 64, "invoice_payment_hash": "a" * 64,
        "bolt11": bolt11.make_demo_invoice(10, "a" * 64), "amount_sats": 10, "key_commitment": "e" * 64,
        "ciphertext_hash": "f" * 64, "key_release": "preimage", "seller_committed_hash": "9" * 64})
    assert r.json()["slashed"] is True
    assert stack.registry.get("/api/tasks/" + t["task_id"]).json()["status"] == "open"  # buyer can re-hire


# ---------------- A6: reputation, restart ----------------

def test_A6_reputation_is_success_rate_not_stake(stack, buyer):
    asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text="Hello world. Second.",
                          budget_sats=100, buyer_pubkey="pk"))
    s = _seller(stack, "sel_summarizer")
    assert 0 <= s["reputation_score"] <= 100 and s["reputation_score"] > 50


def test_A6_restart_does_not_unsuspend(stack):
    assert stack.registry.post("/api/sellers/sel_summarizer/unstake", headers=SK, json={}).status_code == 200
    from registry.seed import bootstrap
    bootstrap()
    from registry import database
    from registry.models import Seller, SellerStatus
    with database.get_db() as db:
        assert db.get(Seller, "sel_summarizer").status == SellerStatus.SUSPENDED


# ---------------- Sweeper (timeouts) ----------------

def test_sweeper_slashes_delivery_timeout_but_not_buyer_no_show(stack):
    from registry import database
    from registry.models import Job, utcnow
    from registry.sweeper import run_sweeper

    t1 = _task(stack)
    no_show = _commit(stack, t1["task_id"]).json()["job_id"]
    t2 = _task(stack)
    stuck = _commit(stack, t2["task_id"]).json()["job_id"]
    stack.registry.post(f"/api/jobs/{stuck}/received", headers=SK, json={"seller_id": "sel_summarizer"})
    with database.get_db() as db:
        db.get(Job, no_show).committed_at = utcnow() - timedelta(hours=1)
        db.get(Job, stuck).received_at = utcnow() - timedelta(hours=1)
    counts = run_sweeper()
    assert counts["commit_timeouts"] == 1 and counts["delivery_timeouts"] == 1
    assert stack.registry.get(f"/api/jobs/{no_show}").json()["status"] == "timeout"
    assert _seller(stack, "sel_summarizer")["stake_sats"] == 9_000  # 10% slash, once


# ---------------- Registration (B10, B11) ----------------

REG = {"lightning_pubkey": "pk_x", "capability": "anything_ok", "price_sats_per_unit": 1, "unit_definition": "u",
       "endpoint_url": "http://127.0.0.1:9", "commitment_endpoint": "http://127.0.0.1:9/commit",
       "docker_image_hash": "sha256:" + "a" * 64}


def test_B11_registration_validation(stack):
    assert stack.registry.post("/api/sellers/register", json={**REG, "price_sats_per_unit": -5}).status_code == 422
    assert stack.registry.post("/api/sellers/register", json={**REG, "capability": "Bad Cap!"}).status_code == 422
    assert stack.registry.post("/api/sellers/register", json={**REG, "commitment_endpoint": "/commit"}).status_code == 400


def test_B10_duplicate_pubkey_is_409_without_sql(stack):
    r1 = stack.registry.post("/api/sellers/register", json=REG)
    assert r1.status_code == 200 and r1.json()["seller_key"].startswith("hsk_")
    r2 = stack.registry.post("/api/sellers/register", json=REG)
    assert r2.status_code == 409 and "INSERT" not in r2.text


def test_registration_outside_demo_grants_no_free_stake(stack, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("MUHR_ALLOW_UNVERIFIED_SELLERS", "true")
    r = stack.registry.post("/api/sellers/register", json={
        **REG, "lightning_pubkey": "02" + "ab" * 32, "endpoint_url": "https://seller.example.com",
        "commitment_endpoint": "https://seller.example.com/commit"})
    assert r.status_code == 200, r.text
    assert r.json()["stake_sats"] == 0


# ---------------- C16 filters ----------------

def test_C16_zero_filters_apply(stack):
    assert stack.registry.get("/api/sellers", params={"max_price": 0}).json()["total"] == 0
    assert stack.registry.get("/api/sellers", params={"min_jobs": 0}).json()["total"] == 3


# ---------------- B7 approvals ----------------

def test_B7_approvals_distinguish_pending_and_rejected(stack, monkeypatch):
    stack.registry.post("/api/approve", json={"request_id": "rq1", "reason": "r", "amount_sats": 1, "task_description": "t"})
    assert stack.registry.get("/api/approve/rq1").json() == {"request_id": "rq1", "status": "pending", "approved": None}
    monkeypatch.setenv("MUHR_ADMIN_KEY", "s3cret")
    assert stack.registry.post("/api/approve", json={"request_id": "rq1", "approved": False}).status_code == 401
    assert stack.registry.post("/api/approve", json={"request_id": "rq1", "approved": False},
                               headers={"X-Muhr-Admin-Key": "s3cret"}).status_code == 200
    assert stack.registry.get("/api/approve/rq1").json()["status"] == "rejected"


def test_C23_rejection_stops_waiting_immediately(stack):
    from buyer_mcp.budget import wait_for_approval
    from buyer_mcp.registry_client import RegistryClient
    stack.registry.post("/api/approve", json={"request_id": "rq2", "reason": "r", "amount_sats": 1, "task_description": "t"})
    stack.registry.post("/api/approve", json={"request_id": "rq2", "approved": False})
    assert asyncio.run(wait_for_approval(RegistryClient("http://registry.test"), "rq2", timeout=30, poll=0.01)) is False


# ---------------- B8 rate limit ----------------

def test_B8_forwarded_for_cannot_dodge_rate_limit(stack, monkeypatch):
    monkeypatch.setenv("MUHR_RATE_LIMIT_REGISTER_PER_MIN", "2")
    codes = [stack.registry.post("/api/sellers/register", json={**REG, "lightning_pubkey": f"pk{i}"},
                                 headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(4)]
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]


# ---------------- C8 / C9 / C11 SSE ----------------

def test_C8_disconnect_removes_only_its_own_queue():
    from registry.sse import Broadcaster
    from shared import schemas
    from registry.models import utcnow

    b = Broadcaster(history=3)

    async def scenario():
        g1, g2 = b.stream(), b.stream()
        await g1.__anext__()
        await g2.__anext__()
        assert b.subscriber_count() == 2
        await g2.aclose()
        assert b.subscriber_count() == 1
        b.publish(schemas.FeedEvent(type="x", timestamp=utcnow(), detail="d", lightning_payment_hash="ab" * 32,
                                    lightning_mode="REAL"))
        frame = await asyncio.wait_for(g1.__anext__(), 2)
        await g1.aclose()
        return frame

    frame = asyncio.run(scenario())
    data = json.loads(frame[len("data: "):])
    assert data["lightning_payment_hash"] == "ab" * 32 and data["lightning_mode"] == "REAL"
    assert data["timestamp"].endswith("Z")
    for i in range(10):
        b.publish(schemas.FeedEvent(type="y", timestamp=utcnow(), detail=str(i)))
    assert len(b.history) == 3


# ---------------- C13 health ----------------

def test_C13_inactive_seller_is_reactivated(stack, monkeypatch):
    from registry import database, health
    from registry.models import Seller, SellerStatus
    with database.get_db() as db:
        db.get(Seller, "sel_summarizer").status = SellerStatus.INACTIVE
    out = asyncio.run(health.health_check_all_sellers())
    assert out["sel_summarizer"] is True
    with database.get_db() as db:
        assert db.get(Seller, "sel_summarizer").status == SellerStatus.ACTIVE


# ---------------- Sellers ----------------

def test_C20_llm_failure_fails_the_job_instead_of_billing(stack, buyer, monkeypatch):
    from buyer_mcp.flow import FlowError
    from sellers import llm_client, processing

    async def boom(*a, **k):
        raise llm_client.AllProvidersFailedError("all down")

    monkeypatch.setattr(llm_client, "configured_providers", lambda *_a: [llm_client.Provider("groq", "m")])
    monkeypatch.setattr(llm_client, "summarize_text", boom)
    monkeypatch.setattr(processing.llm_client, "summarize_text", boom)
    with pytest.raises(FlowError, match="could not complete"):
        asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text="Hi there.",
                              budget_sats=100, buyer_pubkey="pk"))
    jobs = stack.registry.get("/api/jobs").json()["jobs"]
    assert jobs[0]["status"] == "failed"
    assert stack.registry.get("/api/stats").json()["gross_job_volume_sats"] == 0


def test_B4_forged_macaroon_rejected():
    from fastapi import HTTPException
    from sellers import _l402
    mac = _l402.issue_macaroon(job_id="j1", amount_sats=5, payment_hash="a" * 64)
    body, sig = mac.rsplit(".", 1)
    with pytest.raises(HTTPException):
        _l402.verify_macaroon(body + "." + "A" * len(sig))
    pre = crypto_utils.generate_preimage()
    ph = crypto_utils.compute_payment_hash(pre)
    good = _l402.issue_macaroon(job_id="j1", amount_sats=5, payment_hash=ph)
    assert _l402.check_l402(f"L402 {good}:{pre.hex()}", job_id="j1", payment_hash=ph) == pre.hex()
    with pytest.raises(HTTPException):
        _l402.check_l402(f"L402 {good}:{pre.hex()}", job_id="j2", payment_hash=ph)


def test_seller_key_not_released_before_payment(stack, buyer):
    """seller_confirmed path: /key answers 402 until paid."""
    from shared import schemas
    st = stack.summarizer.state.seller
    from sellers.core import JobState
    st.jobs["job_x"] = JobState(task_id="t", price_sats=5, computation_hash="c" * 64, payment_hash="a" * 64,
                                key=b"k" * 32, key_release="seller_confirmed")
    from fastapi.testclient import TestClient
    c = TestClient(stack.summarizer)
    r = c.post("/key", json=schemas.SellerKeyRequest(job_id="job_x", payment_hash="a" * 64).model_dump())
    assert r.status_code == 402


def test_C22_worker_runs_offline_from_request(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    priv, pub = crypto_utils.generate_x25519_keypair()
    key = os.urandom(32)
    req = {"job_id": "job_w", "kind": "classifier", "sealed_input": crypto_utils.seal(pub, b"The patient diagnosis.", "job_w"),
           "result_key_b64": crypto_utils.b64e(key)}
    env = {**os.environ, "MUHR_SELLER_X25519_PRIVATE_B64": crypto_utils.b64e(priv), "PYTHONPATH": str(root)}
    p = subprocess.run([sys.executable, "-m", "sellers.worker"], input=json.dumps(req), capture_output=True,
                       text=True, env=env, cwd=str(root), timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    plain = crypto_utils.decrypt_with_key(key, out["result_ciphertext_b64"], out["result_nonce_b64"],
                                          out["result_tag_b64"], aad=b"job_w")
    assert json.loads(plain)["label"] == "medical"
    assert crypto_utils.hash_result(plain) == out["result_hash"]


# ---------------- B5 buyer refuses bad invoices ----------------

SPEC_INVOICE = ("lnbc2500u1pvjluezpp5qqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqypqdq5xysxxatsyp3k7enxv4jsxqzpuaztrnwngzn3"
                "kdzw5hydlzf03qdgm2hdq27cqv3agm2awhz5se903vruatfhq77w3ls4evs3ch9zw97j25emudupq63nyw24cg27h2rspfj9srp")


def test_bolt11_decodes_spec_vector():
    inv = bolt11.decode(SPEC_INVOICE)
    assert inv.amount_sat == 250_000
    assert inv.payment_hash == "0001020304050607080900010203040506070809000102030405060708090102"
    with pytest.raises(bolt11.InvoiceError):
        bolt11.decode(SPEC_INVOICE[:-1] + "q")


def test_B5_wallet_refuses_wrong_amount_or_hash():
    from buyer_mcp.lightning import LightningWallet, PaymentRefused
    w = LightningWallet(demo_mode=True)
    w.demo_mode = False  # pretend REAL; the checks run before any MDK call
    h = "0001020304050607080900010203040506070809000102030405060708090102"
    with pytest.raises(PaymentRefused, match="amount"):
        asyncio.run(w.pay_invoice(SPEC_INVOICE, expected_amount_sats=100, expected_payment_hash=h, max_amount_sats=100))
    with pytest.raises(PaymentRefused, match="payment_hash"):
        asyncio.run(w.pay_invoice(SPEC_INVOICE, expected_amount_sats=250_000, expected_payment_hash="b" * 64,
                                  max_amount_sats=250_000))


def test_crypto_seal_is_bound_to_job():
    priv, pub = crypto_utils.generate_x25519_keypair()
    sealed = crypto_utils.seal(pub, b"secret", "job_1")
    assert crypto_utils.unseal(priv, sealed, "job_1") == b"secret"
    with pytest.raises(Exception):
        crypto_utils.unseal(priv, sealed, "job_2")


def test_C10_sessions_are_closed():
    from registry import database
    gen = database.get_db_session()
    db = next(gen)
    db.connection()
    gen.close()
    assert not db.in_transaction()
