from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_repo_env() -> None:
    # Load repo-root .env for all services (safe: does nothing if missing).
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(dotenv_path=repo_root / ".env", override=False)


async def main() -> None:
    _load_repo_env()

    # Ensure repo root import works when launched from an MCP client.
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from buyer_mcp.server import main as mcp_main  # noqa: E402

    await mcp_main()


if __name__ == "__main__":
    asyncio.run(main())

