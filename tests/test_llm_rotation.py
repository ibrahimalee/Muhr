"""LLM key rotation (sellers/llm_client.py): which key a job uses, and what happens on 429, 401,
timeouts, bad requests and an empty list. No network: the HTTP client is replaced with a fake."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from sellers import llm_client

KEYS = ["sk-secret-one", "sk-secret-two", "sk-secret-three"]


@pytest.fixture()
def rotation(monkeypatch):
    """Three keys, a scripted fake API, and a record of every request."""
    monkeypatch.setenv("MUHR_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("LLM_API_KEYS", ", ".join(KEYS))
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    llm_client._POOL.reset()

    class Fake:
        calls: list[dict] = []
        script: dict[str, list] = {}  # key -> responses to give in order (then 200 "ok")

    Fake.calls = []
    Fake.script = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"].removeprefix("Bearer ")
        Fake.calls.append({"key": key, "body": json.loads(request.content)})
        queue = Fake.script.get(key, [])
        step = queue.pop(0) if queue else 200
        if isinstance(step, Exception):
            raise step
        if isinstance(step, tuple):  # (status, headers)
            return httpx.Response(step[0], headers=step[1], json={"error": "x"})
        if step == 200:
            return httpx.Response(200, json={"choices": [{"message": {"content": f"ok via {KEYS.index(key) + 1}"}}]})
        return httpx.Response(step, json={"error": "x"})

    monkeypatch.setattr(llm_client, "async_client",
                        lambda timeout=30.0, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout))
    yield Fake
    llm_client._POOL.reset()


def ask() -> str:
    return asyncio.run(llm_client._call_llm("openai/gpt-oss-120b", "hi", 50, 0.2))


def test_each_job_starts_on_the_next_key(rotation):
    assert [ask() for _ in range(4)] == ["ok via 1", "ok via 2", "ok via 3", "ok via 1"]


def test_request_uses_the_key_the_model_and_low_reasoning(rotation):
    ask()
    call = rotation.calls[0]
    assert call["key"] == KEYS[0]
    assert call["body"]["model"] == "openai/gpt-oss-120b"
    assert call["body"]["reasoning_effort"] == "low"


def test_no_reasoning_setting_for_other_models_and_it_can_be_turned_off(rotation, monkeypatch):
    asyncio.run(llm_client._call_llm("llama-3.3-70b-versatile", "hi", 50, 0.2))
    assert "reasoning_effort" not in rotation.calls[-1]["body"]
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    ask()
    assert "reasoning_effort" not in rotation.calls[-1]["body"]


def test_rate_limited_key_hands_over_and_then_rests(rotation):
    rotation.script[KEYS[0]] = [(429, {"retry-after": "30"})]
    assert ask() == "ok via 2"                     # key 1 said 429, key 2 answered
    assert [c["key"] for c in rotation.calls] == [KEYS[0], KEYS[1]]
    rotation.calls.clear()
    results = [ask() for _ in range(4)]            # key 1 is resting: never used again
    assert KEYS[0] not in [c["key"] for c in rotation.calls]
    assert "ok via 1" not in results


def test_rejected_key_is_dropped_for_good(rotation):
    rotation.script[KEYS[1]] = [401]
    results = [ask() for _ in range(6)]
    assert KEYS[1] in [c["key"] for c in rotation.calls][:3]   # tried once...
    assert [c["key"] for c in rotation.calls].count(KEYS[1]) == 1  # ...never again
    assert "ok via 2" not in results


@pytest.mark.parametrize("failure", [httpx.ConnectTimeout("slow"), httpx.ReadTimeout("slow"), 502, 503, 408])
def test_timeout_and_server_errors_move_to_the_next_key(rotation, failure):
    rotation.script[KEYS[0]] = [failure]
    assert ask() == "ok via 2"
    assert [c["key"] for c in rotation.calls] == [KEYS[0], KEYS[1]]


def test_bad_request_is_not_retried_on_other_keys(rotation):
    rotation.script[KEYS[0]] = [400]
    with pytest.raises(llm_client.LLMClientError, match="HTTP 400"):
        ask()
    assert len(rotation.calls) == 1


def test_every_key_rate_limited_fails_fast_without_calling_again(rotation):
    for k in KEYS:
        rotation.script[k] = [(429, {"retry-after": "60"})]
    with pytest.raises(llm_client.LLMClientError, match="rate limited"):
        ask()
    n = len(rotation.calls)
    with pytest.raises(llm_client.LLMClientError, match="every key is rate-limited"):
        ask()
    assert len(rotation.calls) == n               # no request was made


def test_every_key_rejected(rotation):
    for k in KEYS:
        rotation.script[k] = [403]
    with pytest.raises(llm_client.LLMClientError, match="rejected"):
        ask()
    with pytest.raises(llm_client.LLMClientError, match="no usable key"):
        ask()


def test_time_budget_stops_the_rotation(rotation, monkeypatch):
    monkeypatch.setenv("LLM_TOTAL_BUDGET_SECONDS", "0.1")
    with pytest.raises(llm_client.LLMClientError, match="time budget"):
        ask()
    assert rotation.calls == []


def test_keys_never_appear_in_errors_or_logs(rotation, caplog):
    for k in KEYS:
        rotation.script[k] = [429]
    with caplog.at_level("DEBUG"):
        with pytest.raises(llm_client.LLMClientError) as e:
            ask()
    text = str(e.value) + caplog.text
    assert not any(k in text for k in KEYS)
    assert "key 1/3" in text


def test_empty_answer_is_an_error_not_a_rotation(rotation, monkeypatch):
    monkeypatch.setattr(llm_client, "async_client", lambda timeout=30.0, **kw: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None}}]})),
        timeout=timeout))
    with pytest.raises(llm_client.LLMClientError, match="no content"):
        ask()


def test_key_list_parsing(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", " a , ,b,a,  c ,")
    assert llm_client._llm_keys() == ["a", "b", "c"]
    monkeypatch.setenv("LLM_API_KEYS", "")
    assert llm_client._llm_keys() == []


def test_provider_chain_order_and_commitment(rotation, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_real")
    monkeypatch.setenv("GEMINI_API_KEY", "gem_test_not_real")
    names = [p.name for p in llm_client.configured_providers("sel_summarizer")]
    assert names == ["llm", "groq", "gemini"]
    pipeline = llm_client.pipeline_config("summarizer", 500, "sel_summarizer")["pipeline"]
    assert pipeline[0] == "llm:openai/gpt-oss-120b"
    assert not any(k in json.dumps(pipeline) for k in KEYS)


def test_not_configured_without_url_or_keys(rotation, monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", "")
    assert llm_client.configured_providers("sel_summarizer") == []
    monkeypatch.setenv("LLM_API_KEYS", ",".join(KEYS))
    monkeypatch.setenv("LLM_BASE_URL", "")
    assert llm_client.configured_providers("sel_summarizer") == []


def test_private_seller_never_uses_the_hosted_keys(rotation, monkeypatch):
    monkeypatch.setenv("MUHR_SELLER_SEL_URDU_LLM", "lmstudio")
    assert [p.name for p in llm_client.configured_providers("sel_urdu")] == ["lmstudio"]
    assert llm_client.is_private("sel_urdu")
