"""Single place that creates outbound HTTP clients.

Tests register in-process ASGI apps here (``MOUNTS``) so the registry, sellers and
buyer can talk to each other without real sockets.
"""

from __future__ import annotations

import httpx

MOUNTS: dict[str, httpx.AsyncBaseTransport] = {}


def async_client(timeout: float = 30.0, **kwargs) -> httpx.AsyncClient:
    if MOUNTS:
        kwargs.setdefault("mounts", dict(MOUNTS))
    return httpx.AsyncClient(timeout=timeout, **kwargs)
