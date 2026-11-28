"""Rates, receipts, the Urdu seller, the local-model (LM Studio) seller and startup guards."""

from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest

from buyer_mcp.flow import FlowError
from registry.rates import RateCache

URDU = "یہ ایک چھوٹا سا امتحان ہے"
ROMAN = "yeh aik chota sa imtihan hai"


# ---------------- rates ----------------

def test_rates_success_and_cache():
    calls = []
    t = [0.0]
    c = RateCache(fetcher=lambda: calls.append(1) or 28_000_000.0, ttl=600, clock=lambda: t[0])
    a = c.get()
    assert a["btc_pkr"] == 28_000_000.0 and a["sats_pkr"] == pytest.approx(0.28)
    assert a["source"] == "coingecko" and a["stale"] is False
    t[0] = 599
    c.get()
    assert len(calls) == 1          # served from cache
    t[0] = 601
    c.get()
    assert len(calls) == 2          # expired, fetched again


def test_rates_upstream_failure_serves_cached_value_as_stale():
    t = [0.0]
    state = {"ok": True}

    def fetch():
        if not state["ok"]:
            raise httpx.ConnectError("down")
        return 30_000_000.0

    c = RateCache(fetcher=fetch, ttl=10, clock=lambda: t[0])
    c.get()
    state["ok"] = False
    t[0] = 50
    r = c.get()
    assert r["btc_pkr"] == 30_000_000.0 and r["stale"] is True and r["source"] == "coingecko"


def test_rates_upstream_failure_without_cache_uses_env_fallback(monkeypatch):
    monkeypatch.setenv("MUHR_FALLBACK_BTC_PKR", "12345678")

    def boom():
        raise RuntimeError("no network")

    r = RateCache(fetcher=boom).get()
    assert r["source"] == "fallback" and r["stale"] is True
    assert r["btc_pkr"] == 12_345_678.0 and r["sats_pkr"] == pytest.approx(0.12345678)


def test_rates_endpoint_never_errors(stack, monkeypatch):
    from registry import rates

    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(rates, "cache", RateCache(fetcher=boom))
    r = stack.registry.get("/api/rates")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"btc_pkr", "sats_pkr", "source", "fetched_at", "stale"}
    assert body["stale"] is True


# ---------------- receipts ----------------

TEXT = "The contract sets a liability cap. Payment is due within 45 days of invoice."


def _run(buyer, **kw):
    return asyncio.run(buyer.run(buyer_pubkey="buyer_pk", **kw))


def test_receipt_for_settled_job_verifies_and_leaks_nothing(stack, buyer):
    r = _run(buyer, capability="text_summarization", seller_id="sel_summarizer", text=TEXT, budget_sats=100)
    resp = stack.registry.get(f"/api/jobs/{r.job_id}/receipt")
    assert resp.status_code == 200, resp.text
    rec = resp.json()
    assert rec["job_id"] == r.job_id and rec["mode"] == "DEMO"
    assert rec["price_sats"] == r.amount_sats and rec["platform_fee_sats"] == r.amount_sats * 2 // 100
    assert rec["key_release"] == "preimage" and rec["preimage"]
    assert hashlib.sha256(bytes.fromhex(rec["preimage"])).hexdigest() == rec["payment_hash"]
    assert rec["dispute"] == "none"
    # Nothing secret or private is present, by name or by value.
    flat = json.dumps(rec).lower()
    for banned in ("buyer_token", "seller_key", "admin_key", "key_b64", "result_text", "sealed", "bolt11"):
        assert banned not in flat
    assert TEXT.lower() not in flat
    assert not (set(rec) & {"buyer_token", "buyer_pubkey", "api_key_hash", "result_key", "key", "plaintext", "bolt11"})


def test_receipt_404_and_409(stack):
    assert stack.registry.get("/api/jobs/job_nope/receipt").status_code == 404
    task = stack.registry.post("/api/tasks", json={"capability_needed": "text_summarization", "budget_sats": 50,
                                                  "input_schema": {}, "buyer_pubkey": "pk"}).json()
    from fastapi.testclient import TestClient

    commit = TestClient(stack.summarizer).post(
        "/commit", json={"task_id": task["task_id"], "input_schema": {"bytes": 40, "items": 1}, "budget_sats": 50})
    assert commit.status_code == 200, commit.text
    job_id = commit.json()["job_id"]
    assert stack.registry.get(f"/api/jobs/{job_id}/receipt").status_code == 409


# ---------------- Urdu seller ----------------

def test_urdu_quote_is_prorated_with_a_minimum():
    from sellers.core import SellerConfig, quote
    from shared import constants

    cfg = SellerConfig(kind="translator", seller_id="sel_urdu", capability=constants.URDU_CAPABILITY,
                       price_per_unit=constants.URDU_PRICE_PER_UNIT, unit_size=constants.URDU_UNIT_CHARS)
    assert quote(cfg, {"chars": 10}) == 5          # minimum
    assert quote(cfg, {"chars": 1000}) == 8
    assert quote(cfg, {"chars": 2500}) == 20
    assert quote(cfg, {"chars": 5000}) == 40


def test_urdu_seller_is_registered(stack):
    sellers = stack.registry.get("/api/sellers", params={"capability": "urdu_translation"}).json()["sellers"]
    assert [s["seller_id"] for s in sellers] == ["sel_urdu"]
    assert sellers[0]["price_sats_per_unit"] == 8 and sellers[0]["private"] is False


@pytest.mark.parametrize("text", [URDU, ROMAN])
def test_urdu_full_demo_job_and_offline_label(stack, buyer, text):
    r = _run(buyer, capability="urdu_translation", seller_id="sel_urdu", text=text, budget_sats=50)
    assert r.mode == "DEMO"
    assert r.result_text.startswith("[offline demo translation]")
    assert text in r.result_text
    assert stack.registry.get(f"/api/jobs/{r.job_id}/receipt").status_code == 200


def test_urdu_direction_field_is_accepted_and_hidden_from_output(stack, buyer):
    payload = json.dumps({"text": "Good morning", "direction": "en_to_ur"})
    r = _run(buyer, capability="urdu_translation", seller_id="sel_urdu", text=payload, budget_sats=50)
    assert r.result_text == "[offline demo translation]\nGood morning"


def test_urdu_rejects_unknown_direction():
    from sellers import llm_client

    with pytest.raises(llm_client.LLMClientError):
        llm_client.parse_translation_input(json.dumps({"text": "x", "direction": "fr_to_en"}))


def test_urdu_declines_input_over_the_limit(stack, buyer):
    with pytest.raises(FlowError, match="declined"):
        _run(buyer, capability="urdu_translation", seller_id="sel_urdu", text="a" * 5001, budget_sats=500)


# ---------------- demo run limits ----------------

def test_demo_run_rejects_oversized_input(stack):
    r = stack.registry.post("/api/demo/run_e2e", json={"input_text": "x" * 5001, "seller_id": "sel_urdu"})
    assert r.status_code == 422


def test_demo_run_can_target_the_urdu_seller(stack):
    r = stack.registry.post("/api/demo/run_e2e", json={"input_text": ROMAN, "seller_id": "sel_urdu", "budget_sats": 50})
    assert r.status_code == 200, r.text
    assert r.json()["capability"] == "urdu_translation"


# ---------------- LM Studio (private) seller ----------------

def test_private_flag_follows_the_llm_setting(monkeypatch):
    from sellers import llm_client

    monkeypatch.delenv("MUHR_FORCE_OFFLINE", raising=False)
    monkeypatch.delenv("MUHR_FORCE_MOCK", raising=False)
    monkeypatch.setenv("MUHR_SELLER_SEL_URDU_LLM", "lmstudio")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_real")
    assert llm_client.is_private("sel_urdu") is True
    assert [p.name for p in llm_client.configured_providers("sel_urdu")] == ["lmstudio"]   # no hosted fallback
    assert llm_client.is_private("sel_summarizer") is False
    assert [p.name for p in llm_client.configured_providers("sel_summarizer")] == ["groq"]


def test_lmstudio_unreachable_fails_the_job_cleanly(stack, buyer, monkeypatch):
    monkeypatch.delenv("MUHR_FORCE_OFFLINE", raising=False)
    monkeypatch.setenv("MUHR_SELLER_SEL_URDU_LLM", "lmstudio")
    monkeypatch.setenv("MUHR_LMSTUDIO_URL", "http://lmstudio.invalid:1234/v1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_real")      # must NOT be used as a fallback
    with pytest.raises(FlowError, match="could not complete"):
        _run(buyer, capability="urdu_translation", seller_id="sel_urdu", text=URDU, budget_sats=50)
    jobs = stack.registry.get("/api/jobs").json()["jobs"]
    assert jobs[0]["status"] == "failed" and jobs[0]["seller_id"] == "sel_urdu"


def test_lmstudio_success_path(monkeypatch):
    from sellers import llm_client
    from shared import http

    monkeypatch.delenv("MUHR_FORCE_OFFLINE", raising=False)
    monkeypatch.setenv("MUHR_SELLER_SEL_URDU_LLM", "lmstudio")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "This is a small test"}}]})

    monkeypatch.setattr(http, "MOUNTS", {"http://127.0.0.1:1234": httpx.MockTransport(handler)})
    out = asyncio.run(llm_client.translate_text(URDU, seller_id="sel_urdu"))
    assert out.text == "This is a small test" and out.provider == "lmstudio"
    assert seen["url"].endswith("/v1/chat/completions")
    first = seen["body"]["messages"][0]
    assert first["role"] == "system" and "translat" in first["content"].lower()


def test_health_check_records_private_flag(stack, monkeypatch):
    from registry import database, health
    from registry.models import Seller

    monkeypatch.setenv("MUHR_SELLER_SEL_URDU_LLM", "lmstudio")
    monkeypatch.setenv("MUHR_FORCE_OFFLINE", "")
    asyncio.run(health.health_check_all_sellers())
    with database.get_db() as db:
        assert db.get(Seller, "sel_urdu").private is True
        assert db.get(Seller, "sel_summarizer").private is False


# ---------------- startup guards and tool gating ----------------

def test_registry_refuses_to_start_outside_demo_without_keys(monkeypatch):
    from shared import startup

    monkeypatch.setenv("DEMO_MODE", "false")
    for name in ("MUHR_ADMIN_KEY", "MUHR_SELLER_KEY_SEL_SUMMARIZER", "MUHR_SELLER_KEY_SEL_CLASSIFIER", "MUHR_SELLER_KEY_SEL_URDU"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(startup.ConfigError, match="MUHR_ADMIN_KEY"):
        startup.validate_registry_env()
    monkeypatch.setenv("MUHR_ADMIN_KEY", "a" * 24)
    with pytest.raises(startup.ConfigError, match="MUHR_SELLER_KEY_SEL_URDU"):
        startup.validate_registry_env()
    for sid in ("SUMMARIZER", "CLASSIFIER", "URDU"):
        monkeypatch.setenv(f"MUHR_SELLER_KEY_SEL_{sid}", "k" * 24)
    startup.validate_registry_env()


def test_public_demo_deploy_also_requires_the_admin_key(monkeypatch):
    from shared import startup

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("MUHR_PUBLIC_DEPLOY", "true")
    monkeypatch.delenv("MUHR_ADMIN_KEY", raising=False)
    with pytest.raises(startup.ConfigError, match="MUHR_PUBLIC_DEPLOY"):
        startup.validate_registry_env()


def test_local_demo_still_starts_with_zero_config(monkeypatch):
    from shared import startup

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("MUHR_PUBLIC_DEPLOY", raising=False)
    startup.validate_registry_env()
    startup.validate_seller_env("sel_urdu")


def test_seller_refuses_to_start_without_a_key_when_strict(monkeypatch):
    from shared import startup

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.delenv("MUHR_SELLER_KEY", raising=False)
    monkeypatch.delenv("MUHR_SELLER_KEY_SEL_URDU", raising=False)
    with pytest.raises(startup.ConfigError):
        startup.validate_seller_env("sel_urdu")


def test_admin_endpoints_closed_on_public_demo_without_key(stack, monkeypatch):
    monkeypatch.setenv("MUHR_PUBLIC_DEPLOY", "true")
    monkeypatch.delenv("MUHR_ADMIN_KEY", raising=False)
    r = stack.registry.post("/api/approve", json={"request_id": "req_demo_001", "approved": True})
    assert r.status_code in (401, 403, 503)


def test_lightning_send_tool_is_opt_in(monkeypatch):
    from buyer_mcp import server

    monkeypatch.delenv("MUHR_ENABLE_LIGHTNING_SEND", raising=False)
    names = [t.name for t in asyncio.run(server.list_tools())]
    assert "lightning_send" not in names and "send_encrypted_job" in names
    monkeypatch.setenv("MUHR_ENABLE_LIGHTNING_SEND", "true")
    assert "lightning_send" in [t.name for t in asyncio.run(server.list_tools())]


def test_key_released_event_is_emitted_before_settlement(stack, buyer):
    r = _run(buyer, capability="text_summarization", seller_id="sel_summarizer", text=TEXT, budget_sats=100)
    types = [json.loads(d)["type"] for d in stack.feed.history]
    assert "key_released" in types
    assert types.index("lightning_paid") < types.index("key_released") < types.index("payment_settled")
    ev = next(json.loads(d) for d in stack.feed.history if json.loads(d)["type"] == "key_released")
    assert ev["job_id"] == r.job_id and "preimage" in ev["detail"]
