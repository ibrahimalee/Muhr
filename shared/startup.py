"""Startup safety checks shared by the registry and the seller services.

Outside DEMO mode, and in any deployment marked public (``MUHR_PUBLIC_DEPLOY=true``),
the well-known development keys are not acceptable: the process refuses to start
unless the admin key and the seller keys are set.
"""

from __future__ import annotations

import os

from shared import constants

BUILTIN_SELLER_IDS = ("sel_summarizer", "sel_classifier", "sel_urdu")


class ConfigError(RuntimeError):
    pass


def public_deploy() -> bool:
    return constants.env_flag("MUHR_PUBLIC_DEPLOY", False)


def strict() -> bool:
    """True when development fallbacks (insecure keys, open admin endpoints) are not allowed."""
    return (not constants.demo_mode()) or public_deploy()


def _set(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def validate_registry_env() -> None:
    if not strict():
        return
    missing = []
    if not _set("MUHR_ADMIN_KEY"):
        missing.append("MUHR_ADMIN_KEY")
    for sid in BUILTIN_SELLER_IDS:
        name = f"MUHR_SELLER_KEY_{sid.upper()}"
        if not _set(name):
            missing.append(name)
    if missing:
        why = "DEMO_MODE=false" if not constants.demo_mode() else "MUHR_PUBLIC_DEPLOY=true"
        raise ConfigError(f"Refusing to start ({why}): set {', '.join(missing)}")


def validate_seller_env(seller_id: str) -> None:
    if not strict():
        return
    if not (_set("MUHR_SELLER_KEY") or _set(f"MUHR_SELLER_KEY_{seller_id.upper()}")):
        why = "DEMO_MODE=false" if not constants.demo_mode() else "MUHR_PUBLIC_DEPLOY=true"
        raise ConfigError(f"Refusing to start seller {seller_id} ({why}): set MUHR_SELLER_KEY or MUHR_SELLER_KEY_{seller_id.upper()}")
