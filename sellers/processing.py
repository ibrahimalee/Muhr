"""Job processing shared by the seller HTTP app and the isolated worker.

Input arrives sealed to the seller's X25519 key; the result leaves encrypted under
the result key ``K``. Nothing here logs plaintext.
"""

from __future__ import annotations

from dataclasses import dataclass

from sellers import llm_client, offline
from shared import crypto_utils

MAX_TOKENS = {"summarizer": 500, "classifier": 300}


class ProcessingFailed(Exception):
    """The seller could not produce a result (it must not be paid for an error string)."""


@dataclass
class EncryptedResult:
    result_ciphertext_b64: str
    result_nonce_b64: str
    result_tag_b64: str
    result_hash: str
    ciphertext_hash: str
    plaintext_len: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


async def run_pipeline(kind: str, text: str, *, offline_only: bool = False) -> str:
    if offline_only or not llm_client.configured_providers():
        return offline.summarize(text) if kind == "summarizer" else offline.classify(text)
    try:
        if kind == "summarizer":
            return (await llm_client.summarize_text(text, MAX_TOKENS["summarizer"])).text
        return (await llm_client.classify_text(text, MAX_TOKENS["classifier"])).text
    except llm_client.LLMClientError as e:
        raise ProcessingFailed(str(e)) from e


def encrypt_result(job_id: str, result: bytes, key: bytes) -> EncryptedResult:
    ct, nonce, tag = crypto_utils.encrypt_with_key(key, result, aad=job_id.encode("utf-8"))
    return EncryptedResult(ct, nonce, tag, crypto_utils.hash_result(result),
                           crypto_utils.ciphertext_digest(ct, nonce, tag), len(result))


async def process_sealed(kind: str, job_id: str, priv_raw: bytes, sealed: dict, key: bytes,
                         *, offline_only: bool = False) -> EncryptedResult:
    try:
        text = crypto_utils.unseal(priv_raw, sealed, context=job_id).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise ValueError("sealed input could not be opened (wrong key or tampered)") from e
    result = await run_pipeline(kind, text, offline_only=offline_only)
    if not result.strip():
        raise ProcessingFailed("empty result")
    return encrypt_result(job_id, result.encode("utf-8"), key)
