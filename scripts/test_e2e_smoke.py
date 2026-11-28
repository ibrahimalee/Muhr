"""Smoke test against *running* services (registry + both sellers), DEMO Lightning.

    python scripts/test_e2e_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buyer_mcp.budget import BudgetManager  # noqa: E402
from buyer_mcp.flow import BuyerFlow, FlowError  # noqa: E402
from buyer_mcp.lightning import LightningWallet  # noqa: E402
from buyer_mcp.registry_client import RegistryClient  # noqa: E402
from shared import constants  # noqa: E402
from shared.http import async_client  # noqa: E402

TEXT = "The supplier contract caps liability at 1M USD and allows termination with 30 days notice."


async def main() -> int:
    registry_url = os.getenv("REGISTRY_URL", constants.registry_base_url())
    print(f"--- MUHR E2E smoke test ({registry_url}) ---")
    async with async_client(timeout=5.0) as c:
        for name, url in [("registry", registry_url), ("summarizer", constants.seller_summarizer_url()),
                          ("classifier", constants.seller_classifier_url())]:
            try:
                (await c.get(f"{url}/health")).raise_for_status()
                print(f"OK   {name} is up ({url})")
            except Exception as e:  # noqa: BLE001
                print(f"FAIL {name} health check: {e}")
                return 1

    reg = RegistryClient(registry_url)
    flow = BuyerFlow(reg, LightningWallet(demo_mode=True), BudgetManager(daily_budget_sats=10_000, persist=False))
    failed = 0
    for seller_id, cap in [("sel_summarizer", constants.SUMMARIZER_CAPABILITY), ("sel_classifier", constants.CLASSIFIER_CAPABILITY)]:
        try:
            r = await flow.run(capability=cap, seller_id=seller_id, text=TEXT, budget_sats=100, buyer_pubkey="smoke")
            print(f"OK   {seller_id}: job {r.job_id} settled for {r.amount_sats} sats ({r.mode}); result {r.result_text[:60]!r}")
        except FlowError as e:
            print(f"FAIL {seller_id}: {e}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
