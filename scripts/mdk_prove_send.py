"""
Smoke test: one real MDK `send` (requires funded wallet, DEMO_MODE=false, npx).

  python scripts/mdk_prove_send.py --destination "lnbc..." --amount-sats 1
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser(description="MDK send smoke test")
    p.add_argument("--destination", help="BOLT11, lightning address, etc.", required=True)
    p.add_argument("--amount-sats", type=int, help="Omit for amount-encoded bolt11")
    args = p.parse_args()

    sys.path.insert(0, str(_repo_root()))

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=_repo_root() / ".env", override=False)
    # This script is for real sends; do not stay in registry demo mode by accident.
    os.environ["DEMO_MODE"] = "false"

    async def run() -> int:
        from buyer_mcp.lightning import LightningWallet

        w = LightningWallet()
        r = await w.send_lightning(args.destination, args.amount_sats)
        if r.get("success"):
            print("OK", r.get("data", r))
            return 0
        print("ERR", r.get("error", r))
        return 1

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
