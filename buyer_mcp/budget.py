"""Daily spend limit with reservations and human approval for overages.

``reserve`` holds the amount under a lock before any payment, so concurrent jobs
cannot jointly overspend; ``commit`` turns the hold into spend, ``release`` drops
it. State is persisted (default ``~/.muhr/budget.json``) so a restart does not
reset the day's spend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared import constants, schemas

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 300
APPROVAL_POLL_SECONDS = 2.0


class BudgetDenied(Exception):
    pass


class BudgetManager:
    def __init__(self, daily_budget_sats: Optional[int] = None, *, registry=None, persist: bool = True,
                 state_path: Optional[Path] = None) -> None:
        self.daily_budget_sats = daily_budget_sats or int(os.getenv("MUHR_DAILY_BUDGET_SATS", constants.DEFAULT_DAILY_BUDGET_SATS))
        self.registry = registry
        self.persist = persist
        self.state_path = state_path or Path(os.getenv("MUHR_BUDGET_STATE", str(Path.home() / ".muhr" / "budget.json")))
        self.spent_today = 0
        self.reserved = 0
        self.day = self._today()
        self._lock = asyncio.Lock()
        self._load()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _load(self) -> None:
        if not self.persist or not self.state_path.exists():
            return
        try:
            d = json.loads(self.state_path.read_text(encoding="utf-8"))
            if d.get("day") == self.day:
                self.spent_today = int(d.get("spent_today", 0))
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not read budget state %s: %s", self.state_path, e)

    def _save(self) -> None:
        if not self.persist:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"day": self.day, "spent_today": self.spent_today}), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not write budget state %s: %s", self.state_path, e)

    def _check_reset(self) -> None:
        today = self._today()
        if today != self.day:
            self.day, self.spent_today = today, 0
            self._save()

    def remaining(self) -> int:
        self._check_reset()
        return max(0, self.daily_budget_sats - self.spent_today - self.reserved)

    async def reserve(self, amount_sats: int, *, description: str = "") -> None:
        """Hold ``amount_sats`` or raise BudgetDenied. Over-budget asks a human first."""
        async with self._lock:
            self._check_reset()
            if self.spent_today + self.reserved + amount_sats <= self.daily_budget_sats:
                self.reserved += amount_sats
                return
        if not await self._request_approval(amount_sats, description):
            raise BudgetDenied(f"{amount_sats} sats exceeds the daily budget and was not approved")
        async with self._lock:
            self.reserved += amount_sats

    async def commit(self, amount_sats: int) -> None:
        async with self._lock:
            self.reserved = max(0, self.reserved - amount_sats)
            self.spent_today += amount_sats
            self._save()

    async def release(self, amount_sats: int) -> None:
        async with self._lock:
            self.reserved = max(0, self.reserved - amount_sats)

    async def _request_approval(self, amount_sats: int, description: str) -> bool:
        if self.registry is None:
            return False
        overage = self.spent_today + self.reserved + amount_sats - self.daily_budget_sats
        req = schemas.ApprovalRequest(request_id=f"appr_{uuid.uuid4().hex[:12]}",
                                      reason=f"Budget overage: {overage} sats over the daily limit",
                                      amount_sats=amount_sats,
                                      task_description=(description or f"Spend {amount_sats} sats")[:2000])
        try:
            await self.registry.request_approval(req)
            return await wait_for_approval(self.registry, req.request_id)
        except Exception as e:  # noqa: BLE001
            logger.error("Approval request failed: %s", e)
            return False


async def wait_for_approval(registry, request_id: str, timeout: float = APPROVAL_TIMEOUT_SECONDS,
                            poll: float = APPROVAL_POLL_SECONDS) -> bool:
    """True if approved, False if rejected or timed out (rejection returns immediately)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        status = await registry.get_approval_status(request_id)
        if status.status == "approved":
            return True
        if status.status == "rejected":
            return False
        await asyncio.sleep(poll)
    return False
