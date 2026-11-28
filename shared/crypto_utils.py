"""Shared crypto primitives for MUHR.

Two independent secrets protect a job:

1. **Input privacy** (buyer -> seller): the buyer seals its data to the seller's
   X25519 public key (ephemeral ECDH + HKDF + AES-256-GCM). Only that seller can
   open it; the registry never sees plaintext or a hash of it.

2. **Pay-to-decrypt result** (seller -> buyer): the seller encrypts the result
   under a key ``K`` and reports ``sha256(K)`` to the registry. In
   ``preimage`` mode ``K = HKDF(lightning_preimage, job_id)``, so paying the
   invoice *is* receiving the key. Note that HKDF is public: anyone who learns the
   preimage (including routing nodes at settlement) can derive ``K``. That is fine
   for the result because it is only ever sent to the buyer, but it is why the
   *input* is never encrypted under the payment preimage.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_TAG_LEN = 16


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii") if isinstance(s, str) else s, validate=True)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_preimage() -> bytes:
    """32-byte random Lightning preimage."""
    return os.urandom(32)


def compute_payment_hash(preimage: bytes) -> str:
    """payment_hash = SHA256(preimage), hex."""
    return sha256_hex(preimage)


def preimage_matches(preimage_hex: str, payment_hash_hex: str) -> bool:
    try:
        pre = bytes.fromhex(preimage_hex)
    except (ValueError, TypeError):
        return False
    if len(pre) != 32:
        return False
    return hmac.compare_digest(sha256_hex(pre), (payment_hash_hex or "").lower())


def hash_result(result_bytes: bytes) -> str:
    """SHA256 of a plaintext result, hex. Committed to the registry before payment."""
    return sha256_hex(result_bytes)


# ---------------------------------------------------------------------------
# Symmetric AES-256-GCM (wire format: ciphertext / nonce / tag, all base64)
# ---------------------------------------------------------------------------

def encrypt_with_key(key: bytes, plaintext: bytes, aad: bytes | None = None) -> tuple[str, str, str]:
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return b64e(ct[:-_TAG_LEN]), b64e(nonce), b64e(ct[-_TAG_LEN:])


def decrypt_with_key(key: bytes, ciphertext_b64: str, nonce_b64: str, tag_b64: str, aad: bytes | None = None) -> bytes:
    return AESGCM(key).decrypt(b64d(nonce_b64), b64d(ciphertext_b64) + b64d(tag_b64), aad)


def _hkdf(material: bytes, info: bytes, salt: bytes | None = None) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(material)


def derive_result_key(preimage: bytes, job_id: str) -> bytes:
    """Result key for ``preimage`` key-release mode."""
    return _hkdf(preimage, b"muhr-result-key:" + job_id.encode("utf-8"))


def ciphertext_digest(ciphertext_b64: str, nonce_b64: str, tag_b64: str) -> str:
    """Binding hash of an encrypted result, committed by the seller before payment."""
    return sha256_hex(b64d(nonce_b64) + b64d(ciphertext_b64) + b64d(tag_b64))


def key_commitment(key: bytes) -> str:
    """What the seller tells the registry about the result key (sha256, hex)."""
    return sha256_hex(key)


# ---------------------------------------------------------------------------
# X25519 sealed box for buyer -> seller input
# ---------------------------------------------------------------------------

def generate_x25519_keypair() -> tuple[bytes, str]:
    """Return (private_key_raw_bytes, public_key_b64)."""
    priv = X25519PrivateKey.generate()
    return _priv_raw(priv), b64e(_pub_raw(priv.public_key()))


def x25519_public_from_private(priv_raw: bytes) -> str:
    return b64e(_pub_raw(X25519PrivateKey.from_private_bytes(priv_raw).public_key()))


def _priv_raw(priv: X25519PrivateKey) -> bytes:
    return priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def _pub_raw(pub: X25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def seal(recipient_pub_b64: str, plaintext: bytes, context: str) -> dict:
    """Encrypt ``plaintext`` so only the holder of the recipient private key can read it.

    ``context`` (e.g. the job_id) is bound into the key derivation and AAD so a
    sealed payload cannot be replayed into a different job.
    """
    recipient = X25519PublicKey.from_public_bytes(b64d(recipient_pub_b64))
    eph = X25519PrivateKey.generate()
    eph_pub = _pub_raw(eph.public_key())
    shared = eph.exchange(recipient)
    key = _hkdf(shared, b"muhr-seal:" + context.encode("utf-8"), salt=eph_pub)
    ct, nonce, tag = encrypt_with_key(key, plaintext, aad=context.encode("utf-8"))
    return {"ephemeral_pub_b64": b64e(eph_pub), "ciphertext_b64": ct, "nonce_b64": nonce, "tag_b64": tag}


def unseal(priv_raw: bytes, sealed: dict, context: str) -> bytes:
    priv = X25519PrivateKey.from_private_bytes(priv_raw)
    eph_pub = b64d(sealed["ephemeral_pub_b64"])
    shared = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    key = _hkdf(shared, b"muhr-seal:" + context.encode("utf-8"), salt=eph_pub)
    return decrypt_with_key(key, sealed["ciphertext_b64"], sealed["nonce_b64"], sealed["tag_b64"], aad=context.encode("utf-8"))


# ---------------------------------------------------------------------------
# API tokens
# ---------------------------------------------------------------------------

def new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return sha256_hex(token.encode("utf-8"))


def token_matches(token: str | None, expected_hash: str | None) -> bool:
    if not token or not expected_hash:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)
