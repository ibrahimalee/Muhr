from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared import constants  # noqa: E402


def _run_verify(kind: str) -> dict:
    env = os.environ.copy()
    env["MUHR_SELLER_KIND"] = kind
    p = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_seller_docker.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"verify failed:\n{p.stdout}\n{p.stderr}")

    # Parse the last JSON object printed by the verify script (it prints log lines + JSON).
    out_lines = p.stdout.splitlines()
    last_json: dict | None = None
    for i in range(len(out_lines) - 1, -1, -1):
        if out_lines[i].lstrip().startswith("{"):
            candidate = "\n".join(out_lines[i:])
            try:
                last_json = json.loads(candidate)
                break
            except Exception:
                continue

    if last_json is None:
        raise RuntimeError(f"verify produced no parseable JSON:\n{p.stdout}")

    return last_json


def main() -> None:
    kind = os.getenv("MUHR_SELLER_KIND", "summarizer").strip().lower()
    if kind not in {"summarizer", "classifier"}:
        raise SystemExit("Set MUHR_SELLER_KIND to summarizer|classifier")

    verify = _run_verify(kind)
    docker_image_hash = verify["docker_image_hash"]

    endpoint_url = (constants.seller_summarizer_url() if kind == "summarizer" else constants.seller_classifier_url()).rstrip("/")
    capability = constants.SUMMARIZER_CAPABILITY if kind == "summarizer" else constants.CLASSIFIER_CAPABILITY
    price = constants.SUMMARIZER_PRICE_PER_UNIT if kind == "summarizer" else constants.CLASSIFIER_PRICE_PER_UNIT
    unit = constants.SUMMARIZER_UNIT if kind == "summarizer" else constants.CLASSIFIER_UNIT

    req = {
        # Outside DEMO this must be your node's 33-byte compressed pubkey (66 hex chars).
        "lightning_pubkey": os.getenv("MUHR_SELLER_NODE_PUBKEY", f"demo_{kind}_pubkey"),
        "capability": capability,
        "price_sats_per_unit": price,
        "unit_definition": unit,
        "endpoint_url": endpoint_url,
        "commitment_endpoint": f"{endpoint_url}{constants.API_SELLER_COMMIT}",
        "docker_image_hash": docker_image_hash,
        "optimal_input_schema": {"type": "string"},
    }

    registry = os.getenv("REGISTRY_URL", constants.registry_base_url()).rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        r = client.post(f"{registry}{constants.API_SELLERS_REGISTER}", json=req)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                "Registry rejected seller registration.\n"
                f"Status: {r.status_code}\n"
                f"Body: {r.text}\n"
            ) from e
        reg = r.json()
        print(json.dumps({"verified": True, "registered": {k: v for k, v in reg.items() if k != "seller_key"}}, indent=2))
        # The seller key is shown once: store it as MUHR_SELLER_KEY for the seller process.
        print(f"
SELLER KEY (shown once, set MUHR_SELLER_KEY on the seller): {reg['seller_key']}", file=sys.stderr)


if __name__ == "__main__":
    main()

