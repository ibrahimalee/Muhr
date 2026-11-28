"""Isolated job runner for ``docker run --network=none``.

stdin : {"job_id", "kind", "sealed_input": {...}, "result_key_b64"}
env   : MUHR_SELLER_X25519_PRIVATE_B64 (the seller's input-decryption key)
stdout: {"result_ciphertext_b64", "result_nonce_b64", "result_tag_b64", "result_hash", "ciphertext_hash", ...}

The seller HTTP process never sees the plaintext input or result in this mode:
the worker opens the sealed input, runs the offline pipeline (no network), and
returns only the encrypted result plus its commitments.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sellers.processing import process_sealed
from shared import crypto_utils


def _bail(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(2)


async def main() -> None:
    try:
        req = json.loads(sys.stdin.read())
        job_id = str(req["job_id"])
        kind = str(req.get("kind", "summarizer"))
        sealed = req["sealed_input"]
        key = crypto_utils.b64d(req["result_key_b64"])
    except Exception as e:  # noqa: BLE001
        _bail(f"Invalid worker request: {e.__class__.__name__}: {e}")
    priv_b64 = os.getenv("MUHR_SELLER_X25519_PRIVATE_B64", "").strip()
    if not priv_b64:
        _bail("Missing MUHR_SELLER_X25519_PRIVATE_B64")
    try:
        out = await process_sealed(kind, job_id, crypto_utils.b64d(priv_b64), sealed, key, offline_only=True)
    except Exception as e:  # noqa: BLE001
        _bail(f"Processing failed: {e}")
    sys.stdout.write(json.dumps(out.to_dict()))


if __name__ == "__main__":
    asyncio.run(main())
