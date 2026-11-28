"""Minimal BOLT-11 decoder (amount, payment hash, expiry) plus MUHR demo invoices.

The buyer uses this to check an invoice *before* paying it:
the amount must equal the accepted job price and the payment hash must equal the
one the seller reported to the registry. Signature verification is not needed
for that check (the payee identity is pinned by the hash the registry stores).

DEMO invoices look like ``muhrdemo:<amount_sats>:<payment_hash_hex>``. They are
deliberately not valid Lightning invoices so no wallet can ever try to pay one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_GEN = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_HRP_RE = re.compile(r"^ln(bcrt|bc|tbs|tb|sb)(\d+)?([munp])?$")
_MSAT_PER_BTC = 100_000_000_000
DEMO_PREFIX = "muhrdemo:"


class InvoiceError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedInvoice:
    network: str
    amount_msat: Optional[int]
    payment_hash: str
    timestamp: Optional[int]
    expiry_seconds: Optional[int]
    demo: bool = False

    @property
    def amount_sat(self) -> Optional[int]:
        return None if self.amount_msat is None else self.amount_msat // 1000


def make_demo_invoice(amount_sats: int, payment_hash: str) -> str:
    return f"{DEMO_PREFIX}{int(amount_sats)}:{payment_hash.lower()}"


def _polymod(values: list[int]) -> int:
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= _GEN[i] if ((top >> i) & 1) else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_decode(s: str) -> tuple[str, list[int]]:
    if s.lower() != s and s.upper() != s:
        raise InvoiceError("mixed case")
    s = s.lower()
    pos = s.rfind("1")
    if pos < 1 or pos + 7 > len(s):
        raise InvoiceError("missing bech32 separator")
    hrp, data_part = s[:pos], s[pos + 1:]
    try:
        data = [_CHARSET.index(c) for c in data_part]
    except ValueError as e:
        raise InvoiceError("invalid bech32 character") from e
    if _polymod(_hrp_expand(hrp) + data) != 1:
        raise InvoiceError("bad bech32 checksum")
    return hrp, data[:-6]


def _words_to_int(words: list[int]) -> int:
    n = 0
    for w in words:
        n = (n << 5) | w
    return n


def _words_to_bytes(words: list[int]) -> bytes:
    bits = 0
    acc = 0
    out = bytearray()
    for w in words:
        acc = (acc << 5) | w
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    return bytes(out)


def _parse_amount(digits: Optional[str], mult: Optional[str]) -> Optional[int]:
    if digits is None:
        if mult:
            raise InvoiceError("multiplier without amount")
        return None
    n = int(digits)
    if mult is None:
        return n * _MSAT_PER_BTC
    if mult == "m":
        return n * 100_000_000
    if mult == "u":
        return n * 100_000
    if mult == "n":
        return n * 100
    # pico-BTC: 1 p = 0.1 msat
    if n % 10:
        raise InvoiceError("sub-millisatoshi amount")
    return n // 10


def decode(invoice: str) -> DecodedInvoice:
    inv = (invoice or "").strip()
    if inv.lower().startswith("lightning:"):
        inv = inv[len("lightning:"):]
    if inv.startswith(DEMO_PREFIX):
        parts = inv[len(DEMO_PREFIX):].split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not re.fullmatch(r"[0-9a-f]{64}", parts[1]):
            raise InvoiceError("malformed demo invoice")
        return DecodedInvoice("demo", int(parts[0]) * 1000, parts[1], None, None, demo=True)

    hrp, data = _bech32_decode(inv)
    m = _HRP_RE.match(hrp)
    if not m:
        raise InvoiceError(f"unrecognised invoice prefix {hrp!r}")
    network, digits, mult = m.groups()
    amount_msat = _parse_amount(digits, mult)

    if len(data) < 7 + 104:
        raise InvoiceError("invoice too short")
    timestamp = _words_to_int(data[:7])
    tagged = data[7:-104]  # strip 520-bit signature
    payment_hash: Optional[str] = None
    expiry: Optional[int] = None
    i = 0
    while i + 3 <= len(tagged):
        tag = tagged[i]
        length = tagged[i + 1] * 32 + tagged[i + 2]
        field = tagged[i + 3:i + 3 + length]
        i += 3 + length
        if tag == 1 and length == 52 and payment_hash is None:   # 'p'
            payment_hash = _words_to_bytes(field)[:32].hex()
        elif tag == 6:                                            # 'x'
            expiry = _words_to_int(field)
    if not payment_hash:
        raise InvoiceError("invoice has no payment hash")
    return DecodedInvoice(network, amount_msat, payment_hash, timestamp, expiry if expiry is not None else 3600)
