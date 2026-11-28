"""HTTP client for the registry and sellers, used by the buyer flow."""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from shared import constants, schemas
from shared.http import async_client

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    def __init__(self, status: int, detail: str, url: str) -> None:
        super().__init__(f"HTTP {status} from {url}: {detail}")
        self.status = status
        self.detail = detail


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        detail = r.json().get("detail", r.text)
    except Exception:  # noqa: BLE001
        detail = r.text
    raise RegistryError(r.status_code, str(detail)[:500], str(r.request.url))


class RegistryClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 20.0) -> None:
        # REGISTRY_URL is an alternative name some MCP client configs use.
        self.base_url = (base_url or os.getenv("REGISTRY_URL", "").strip() or constants.registry_base_url()).rstrip("/")
        self.timeout = timeout

    async def _request(self, method: str, url: str, *, json: Optional[dict] = None, params: Optional[dict] = None,
                       headers: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
        async with async_client(timeout=timeout or self.timeout) as client:
            r = await client.request(method, url, json=json, params=params, headers=headers)
        _raise_for(r)
        return r.json()

    def _reg(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _buyer(token: str) -> dict:
        return {constants.HEADER_BUYER_TOKEN: token}

    # ---- registry ----
    async def get_sellers(self, capability: Optional[str] = None, max_price: Optional[int] = None,
                          min_jobs: Optional[int] = None) -> schemas.SellerListResponse:
        params = {k: v for k, v in {"capability": capability, "max_price": max_price, "min_jobs": min_jobs}.items()
                  if v is not None and v != ""}
        return schemas.SellerListResponse(**await self._request("GET", self._reg(constants.API_SELLERS), params=params))

    async def post_task(self, req: schemas.TaskPostRequest) -> schemas.TaskPostResponse:
        return schemas.TaskPostResponse(**await self._request("POST", self._reg(constants.API_TASKS),
                                                              json=req.model_dump(exclude_none=True)))

    async def get_job(self, job_id: str) -> schemas.JobSummary:
        return schemas.JobSummary(**await self._request("GET", self._reg(constants.API_JOB.format(job_id=job_id))))

    async def record_payment(self, job_id: str, token: str, req: schemas.JobPaymentRequest) -> schemas.JobPaymentResponse:
        return schemas.JobPaymentResponse(**await self._request(
            "POST", self._reg(constants.API_JOB_PAYMENT.format(job_id=job_id)), json=req.model_dump(), headers=self._buyer(token)))

    async def settle(self, job_id: str, token: str) -> dict:
        return await self._request("POST", self._reg(constants.API_JOB_SETTLE.format(job_id=job_id)), headers=self._buyer(token))

    async def dispute(self, job_id: str, token: str, req: schemas.DisputeRequest) -> schemas.DisputeResponse:
        return schemas.DisputeResponse(**await self._request(
            "POST", self._reg(constants.API_JOB_DISPUTE.format(job_id=job_id)), json=req.model_dump(), headers=self._buyer(token)))

    async def request_approval(self, req: schemas.ApprovalRequest) -> dict:
        return await self._request("POST", self._reg(constants.API_APPROVE), json=req.model_dump())

    async def get_approval_status(self, request_id: str) -> schemas.ApprovalStatusResponse:
        return schemas.ApprovalStatusResponse(**await self._request("GET", self._reg(f"/api/approve/{request_id}")))

    # ---- seller ----
    async def seller_commit(self, seller_url: str, req: schemas.SellerCommitRequest) -> schemas.SellerCommitResponse:
        return schemas.SellerCommitResponse(**await self._request("POST", f"{seller_url.rstrip('/')}{constants.API_SELLER_COMMIT}",
                                                                  json=req.model_dump()))

    async def seller_job(self, seller_url: str, req: schemas.SellerJobRequest) -> schemas.SellerJobResponse:
        # LLM work can take a while; this is the one long call.
        return schemas.SellerJobResponse(**await self._request("POST", f"{seller_url.rstrip('/')}{constants.API_SELLER_JOB}",
                                                               json=req.model_dump(), timeout=180.0))

    async def seller_key(self, seller_url: str, req: schemas.SellerKeyRequest, *, l402: Optional[str] = None) -> schemas.SellerKeyResponse:
        headers = {"Authorization": f"L402 {l402}"} if l402 else None
        return schemas.SellerKeyResponse(**await self._request("POST", f"{seller_url.rstrip('/')}{constants.API_SELLER_KEY}",
                                                               json=req.model_dump(), headers=headers))

    async def seller_demo_pay(self, seller_url: str, req: schemas.DemoPayRequest) -> schemas.DemoPayResponse:
        return schemas.DemoPayResponse(**await self._request("POST", f"{seller_url.rstrip('/')}{constants.API_SELLER_DEMO_PAY}",
                                                             json=req.model_dump()))
