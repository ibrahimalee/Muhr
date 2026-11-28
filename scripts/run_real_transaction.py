"""Run one MUHR job end to end against running services and print a JSON receipt.

    python scripts/run_real_transaction.py                 # DEMO (no sats move)
    python scripts/run_real_transaction.py --real          # MDK wallet pays a real invoice
    python scripts/run_real_transaction.py --seller sel_classifier --text "..."

Needs the registry (default :8000) and the chosen seller running. With --real,
DEMO_MODE=false must also be set for the *seller* so it issues a real invoice,
and the buyer MDK wallet must be funded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(dotenv_path=REPO_ROOT / ".env", override=False)

from buyer_mcp.budget import BudgetManager  # noqa: E402
from buyer_mcp.flow import BuyerFlow, FlowError  # noqa: E402
from buyer_mcp.lightning import LightningWallet  # noqa: E402
from buyer_mcp.registry_client import RegistryClient  # noqa: E402
from shared import constants  # noqa: E402

DEFAULT_TEXT = ("Patient has mild fever and cough for three days. Possible influenza. "
                "No travel history. Recommend rest, fluids and a follow-up if symptoms worsen.")


async def run(args: argparse.Namespace) -> int:
    registry = RegistryClient(args.registry)
    wallet = LightningWallet(demo_mode=not args.real)
    if args.real and wallet.demo_mode:
        print(json.dumps({"ok": False, "stage": "wallet", "detail": "npx/MDK unavailable; cannot pay for real"}))
        return 1
    budget = BudgetManager(daily_budget_sats=max(args.budget, constants.DEFAULT_DAILY_BUDGET_SATS), registry=registry)
    sellers = await registry.get_sellers()
    seller = next((s for s in sellers.sellers if s.seller_id == args.seller), None)
    if seller is None:
        print(json.dumps({"ok": False, "stage": "discovery", "detail": f"{args.seller} is not an active seller"}))
        return 1
    before = await wallet.wallet_status()
    try:
        r = await BuyerFlow(registry, wallet, budget).run(capability=seller.capability, seller_id=seller.seller_id,
                                                          text=args.text, budget_sats=args.budget, buyer_pubkey="script_buyer")
    except FlowError as e:
        print(json.dumps({"ok": False, "stage": "flow", "detail": str(e)}, indent=2))
        return 1
    after = await wallet.wallet_status()
    print(json.dumps({
        "ok": True, "task_id": r.task_id, "job_id": r.job_id, "seller_id": r.seller_id, "mode": r.mode,
        "amount_sats": r.amount_sats, "payment_hash": r.payment_hash, "payment_verified_by": r.payment_verified_by,
        "result_hash": r.result_hash, "result_preview": r.result_text[:300],
        "wallet_balance_before": before.get("balance_sats"), "wallet_balance_after": after.get("balance_sats"),
    }, indent=2))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--registry", default=os.getenv("REGISTRY_URL", constants.registry_base_url()))
    p.add_argument("--seller", default=os.getenv("DEMO_SELLER_ID", "sel_summarizer"))
    p.add_argument("--text", default=os.getenv("DEMO_JOB_DATA", DEFAULT_TEXT))
    p.add_argument("--budget", type=int, default=int(os.getenv("DEMO_BUDGET_SATS", "100")))
    p.add_argument("--real", action="store_true", help="Pay with the MDK wallet (real sats)")
    raise SystemExit(asyncio.run(run(p.parse_args())))


if __name__ == "__main__":
    main()
