"""Real-Lightning variant of ``run_real_transaction.py`` (kept for existing docs/commands).

    python scripts/run_real_lightning_demo.py [--seller sel_summarizer] [--budget 50]

Requires DEMO_MODE=false for the seller and buyer, Node.js (npx) and a funded MDK wallet.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_real_transaction import main  # noqa: E402

if __name__ == "__main__":
    if "--real" not in sys.argv:
        sys.argv.append("--real")
    main()
