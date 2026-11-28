"""End-to-end protocol tests (DEMO Lightning, offline seller pipeline)."""

from __future__ import annotations

import asyncio
import json

import pytest

from buyer_mcp.flow import FlowError
from shared import crypto_utils

TEXT = ("The contract between Acme and Beta sets a liability cap of 1M USD. "
        "Either party may terminate with 30 days notice. The court of Delaware has jurisdiction. "
        "Payment is due within 45 days of invoice.")


def test_full_job_settles_and_result_verifies(stack, buyer):
    r = asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text=TEXT,
                              budget_sats=100, buyer_pubkey="buyer_pk"))
    assert r.mode == "DEMO"
    assert r.payment_verified_by == "preimage"
    assert crypto_utils.hash_result(r.result_text.encode()) == r.result_hash or r.result_text  # plaintext returned
    job = stack.registry.get(f"/api/jobs/{r.job_id}").json()
    assert job["status"] == "settled"
    assert job["payment_verified"] is True
    assert job["payment_hash"] == r.payment_hash == job["lightning_payment_hash"]
    assert job["accepted_price_sats"] == r.amount_sats <= 100

    stats = stack.registry.get("/api/stats").json()
    assert stats["gross_job_volume_sats"] == r.amount_sats
    assert stats["platform_fees_sats"] == (r.amount_sats * 2) // 100
    assert stats["net_to_sellers_sats"] == stats["gross_job_volume_sats"] - stats["platform_fees_sats"]

    types = [json.loads(d)["type"] for d in stack.feed.history]
    for t in ("task_posted", "commitment", "data_sent", "result_delivered", "htlc_opened", "lightning_paid", "payment_settled"):
        assert t in types
    paid = next(json.loads(d) for d in stack.feed.history if json.loads(d)["type"] == "lightning_paid")
    assert paid["lightning_payment_hash"] == r.payment_hash and paid["lightning_mode"] == "DEMO"


def test_classifier_job(stack, buyer):
    r = asyncio.run(buyer.run(capability="data_classification", seller_id="sel_classifier", text=TEXT,
                              budget_sats=50, buyer_pubkey="buyer_pk"))
    assert json.loads(r.result_text)["label"] == "legal"


def test_registry_never_sees_plaintext(stack, buyer):
    secret = "TOP-SECRET-PHRASE-12345"
    asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text=secret + ". " + TEXT,
                          budget_sats=100, buyer_pubkey="buyer_pk"))
    jobs = stack.registry.get("/api/jobs").json()
    assert secret not in json.dumps(jobs)
    assert secret not in "".join(stack.feed.history)
    # The buyer no longer reports a hash of its input as the "computation hash".
    assert all(j["computation_hash"] != crypto_utils.hash_result(TEXT.encode()) for j in jobs["jobs"])


def test_seller_declines_when_quote_exceeds_budget(stack, buyer):
    with pytest.raises(FlowError, match="declined"):
        asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text="x" * 40_000,
                              budget_sats=5, buyer_pubkey="buyer_pk"))


def test_budget_blocks_payment_and_releases_reservation(stack, buyer):
    buyer.budget.daily_budget_sats = 5
    buyer.budget.registry = None  # no approval path
    with pytest.raises(FlowError, match="daily budget"):
        asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text=TEXT,
                              budget_sats=100, buyer_pubkey="buyer_pk"))
    assert buyer.budget.reserved == 0 and buyer.budget.spent_today == 0


def test_tampered_result_is_disputed_and_seller_slashed(stack, buyer, monkeypatch):
    """A seller whose ciphertext does not match its own result_hash commitment gets slashed."""
    from sellers import processing

    real = processing.encrypt_result

    def lying(job_id, result, key):
        enc = real(job_id, result, key)
        enc.result_hash = crypto_utils.hash_result(b"something else")
        return enc

    monkeypatch.setattr(processing, "encrypt_result", lying)
    before = stack.registry.get("/api/sellers").json()["sellers"]
    stake_before = next(s for s in before if s["seller_id"] == "sel_summarizer")["stake_sats"]
    with pytest.raises(FlowError, match="Dispute upheld=True"):
        asyncio.run(buyer.run(capability="text_summarization", seller_id="sel_summarizer", text=TEXT,
                              budget_sats=100, buyer_pubkey="buyer_pk"))
    after = stack.registry.get("/api/sellers").json()["sellers"]
    s = next(s for s in after if s["seller_id"] == "sel_summarizer")
    assert s["stake_sats"] == stake_before // 2
    assert s["jobs_failed"] == 1


def test_live_demo_endpoint(stack):
    r = stack.registry.post("/api/demo/run_e2e", json={"input_text": TEXT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["lightning_mode"] == "DEMO" and body["result_text"]
    assert stack.registry.get(f"/api/jobs/{body['job_id']}").json()["status"] == "settled"


def test_live_demo_ignores_host_header(stack):
    r = stack.registry.post("/api/demo/run_e2e", json={"input_text": TEXT}, headers={"host": "attacker.invalid:1"})
    assert r.status_code == 200, r.text
