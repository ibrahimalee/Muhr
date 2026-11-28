"""Check the LLM settings in the repo-root .env without printing any key.

    python scripts/check_llm.py                      # test every key, then one sample translation
    python scripts/check_llm.py --model llama-3.3-70b-versatile   # try another model

It reads LLM_BASE_URL, LLM_API_KEYS and LLM_MODEL (the same ones the sellers use), sends one tiny
request per key, and prints the HTTP status and time for each ("key 2/5"), never the key itself.
Then it runs one Urdu-to-English translation through the real rotation code and prints the answer.
Hosted providers see what you send; the sample text here is a harmless greeting.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(dotenv_path=ROOT / ".env")

from sellers import llm_client  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="use this model instead of LLM_MODEL")
    args = ap.parse_args()
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    base, keys, model = llm_client._llm_base_url(), llm_client._llm_keys(), llm_client._llm_model()
    print(f"Base URL : {base or '(not set)'}")
    print(f"Model    : {model}")
    print(f"Keys     : {len(keys)}")
    if not base or not keys:
        print("\nSet LLM_BASE_URL and LLM_API_KEYS (keys separated by commas) in .env first.")
        return 1

    print("\nEach key, one tiny request:")
    good = 0
    for i, key in enumerate(keys, 1):
        t0 = time.monotonic()
        try:
            r = httpx.post(f"{base}/chat/completions", timeout=30.0,
                           headers={"Authorization": f"Bearer {key}"},
                           json={"model": model, "max_tokens": 16, "messages": [{"role": "user", "content": "Say ok."}]})
            note = {200: "works", 401: "rejected (wrong or revoked key)", 403: "rejected (not allowed)",
                    429: "rate limited right now (it will rest, then work again)"}.get(r.status_code, "unexpected")
            print(f"  key {i}/{len(keys)}: HTTP {r.status_code} in {time.monotonic() - t0:.1f}s, {note}")
            good += r.status_code == 200
        except httpx.HTTPError as e:
            print(f"  key {i}/{len(keys)}: failed ({e.__class__.__name__})")
    print(f"\n{good} of {len(keys)} keys answered.")

    print("\nSample translation through the real rotation code (Urdu to English):")
    sample = "السلام علیکم، آپ کا دن کیسا گزرا؟ میں آج لاہور جا رہا ہوں۔"
    try:
        res = asyncio.run(llm_client.translate_text(sample, max_tokens=300))
        print(f"  provider: {res.provider}, model: {res.model}")
        print(f"  answer  : {res.text}")
    except llm_client.LLMClientError as e:
        print(f"  failed: {e}")
        return 1
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
