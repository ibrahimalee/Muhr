"""Test harness: registry + both sellers + buyer wired together in-process.

Every outbound HTTP call goes through ``shared.http.MOUNTS``, which maps fake
hostnames to the ASGI apps, so no sockets or real Lightning are involved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Must be set before any MUHR module loads the repo .env (load_dotenv never overrides).
os.environ.update({
    "DEMO_MODE": "true",
    "MUHR_DISABLE_HEALTH_SCHEDULER": "true",
    "MUHR_SEED_DEMO_DATA": "false",
    "MUHR_SEED_DEMO_APPROVAL": "false",
    "MUHR_REGISTRY_BASE_URL": "http://registry.test",
    "MUHR_REGISTRY_INTERNAL_URL": "http://registry.test",
    "MUHR_SELLER_SUMMARIZER_URL": "http://summarizer.test",
    "MUHR_SELLER_CLASSIFIER_URL": "http://classifier.test",
    "MUHR_SELLER_URDU_URL": "http://urdu.test",
    "MUHR_FORCE_OFFLINE": "1",
    "GROQ_API_KEY": "",
    "LLM_BASE_URL": "",
    "LLM_API_KEYS": "",
    "GEMINI_API_KEY": "",
    "MUHR_ADMIN_KEY": "",
    "MUHR_SELLER_KEY": "",
    "MUHR_SELLER_ISOLATION": "none",
    "MUHR_TRUST_PROXY": "false",
})

import httpx  # noqa: E402

from registry import database  # noqa: E402


@pytest.fixture()
def stack(monkeypatch, tmp_path):
    """Fresh DB + feed; returns a namespace with clients for every component."""
    database.configure(f"sqlite:///{(tmp_path / 'muhr_test.db').as_posix()}")

    import registry.main as registry_main
    from registry import auth
    from registry.seed import bootstrap
    from registry.sse import broadcaster
    from sellers.classifier.app import app as classifier_app
    from sellers.summarizer.app import app as summarizer_app
    from sellers.urdu.app import app as urdu_app
    from shared import http

    broadcaster.history.clear()
    auth.limiter.reset()
    for app in (summarizer_app, classifier_app, urdu_app):
        app.state.seller.jobs.clear()
    bootstrap()

    monkeypatch.setattr(http, "MOUNTS", {
        "http://registry.test": httpx.ASGITransport(app=registry_main.app),
        "http://summarizer.test": httpx.ASGITransport(app=summarizer_app),
        "http://classifier.test": httpx.ASGITransport(app=classifier_app),
        "http://urdu.test": httpx.ASGITransport(app=urdu_app),
    })

    from fastapi.testclient import TestClient

    class Stack:
        registry = TestClient(registry_main.app)
        main = registry_main
        summarizer = summarizer_app
        classifier = classifier_app
        urdu = urdu_app
        feed = broadcaster

    yield Stack
    Stack.registry.close()


@pytest.fixture()
def buyer(stack, tmp_path):
    from buyer_mcp.budget import BudgetManager
    from buyer_mcp.flow import BuyerFlow
    from buyer_mcp.lightning import LightningWallet
    from buyer_mcp.registry_client import RegistryClient

    reg = RegistryClient("http://registry.test")
    return BuyerFlow(reg, LightningWallet(demo_mode=True),
                     BudgetManager(daily_budget_sats=10_000, registry=reg, persist=False))

