"""The buyer side of a MUHR job, end to end.

Used by the MCP server, the scripts and the registry's live-demo endpoint, so
there is exactly one implementation of the protocol on the buyer side.

What the buyer checks before paying (all against the registry, not the seller):
- the job belongs to the seller it hired and is at the price that seller quoted;
- the invoice amount equals that price and its payment hash equals the one the
  seller committed to the registry, together with sha256(result), sha256(key)
  and sha256(ciphertext);
- the daily budget has room (reserved under a lock).
After paying it obtains the key, decrypts, verifies sha256(result), and either
settles or files a dispute the registry can adjudicate without trusting anyone.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from buyer_mcp.budget import BudgetDenied, BudgetManager
from buyer_mcp.lightning import LightningWallet, PaymentRefused
from buyer_mcp.registry_client import RegistryClient, RegistryError
from shared import bolt11, constants, crypto_utils, schemas

logger = logging.getLogger(__name__)

KEY_POLL_SECONDS = 60.0


class FlowError(Exception):
    pass


@dataclass
class JobResult:
    task_id: str
    job_id: str
    seller_id: str
    amount_sats: int
    payment_hash: str
    mode: str
    result_hash: str
    result_text: str
    payment_verified_by: Optional[str]


@dataclass
class _TaskTicket:
    token: str
    budget_sats: int
    capability: str


class BuyerFlow:
    def __init__(self, registry: RegistryClient, wallet: LightningWallet, budget: BudgetManager) -> None:
        self.registry = registry
        self.wallet = wallet
        self.budget = budget
        self._tasks: dict[str, _TaskTicket] = {}

    async def post_task(self, *, capability: str, budget_sats: int, buyer_pubkey: str,
                        input_schema: Optional[dict] = None, expiry_seconds: int = 300) -> schemas.TaskPostResponse:
        resp = await self.registry.post_task(schemas.TaskPostRequest(
            capability_needed=capability, input_schema=input_schema or {}, budget_sats=budget_sats,
            expiry_seconds=expiry_seconds, buyer_pubkey=buyer_pubkey))
        self._tasks[resp.task_id] = _TaskTicket(resp.buyer_token, budget_sats, capability)
        return resp

    async def run(self, *, capability: str, seller_id: str, text: str, budget_sats: int, buyer_pubkey: str) -> JobResult:
        task = await self.post_task(capability=capability, budget_sats=budget_sats, buyer_pubkey=buyer_pubkey,
                                    input_schema=describe_input(text))
        return await self.hire(task.task_id, seller_id, text)

    async def hire(self, task_id: str, seller_id: str, text: str) -> JobResult:
        ticket = self._tasks.get(task_id)
        if ticket is None:
            raise FlowError(f"Unknown task {task_id}: post it with this buyer first (the buyer token is held in memory)")
        sellers = await self.registry.get_sellers(capability=ticket.capability)
        seller = next((s for s in sellers.sellers if s.seller_id == seller_id), None)
        if seller is None:
            raise FlowError(f"Seller {seller_id} is not an active {ticket.capability} seller")
        url = seller.endpoint_url

        # 1) Quote + commitment (the seller registers the job with its own key).
        try:
            commit = await self.registry.seller_commit(url, schemas.SellerCommitRequest(
                task_id=task_id, input_schema=describe_input(text), budget_sats=ticket.budget_sats))
        except RegistryError as e:
            raise FlowError(f"Seller commit failed: {e.detail}") from e
        if not commit.accepted or not commit.job_id:
            raise FlowError(f"Seller declined: quoted {commit.price_sats} sats for a {ticket.budget_sats}-sat budget")
        price = int(commit.price_sats or 0)
        job = await self.registry.get_job(commit.job_id)
        if job.seller_id != seller_id or job.accepted_price_sats != price or job.computation_hash != commit.computation_hash:
            raise FlowError("Registry job record does not match the seller's commitment")
        if not commit.seller_pubkey_b64:
            raise FlowError("Seller did not provide an encryption key")
        job_id = commit.job_id

        # 2) Reserve budget before any work is paid for.
        try:
            await self.budget.reserve(price, description=f"{ticket.capability} job {job_id} from {seller_id}")
        except BudgetDenied as e:
            raise FlowError(str(e)) from e

        paid = False
        try:
            # 3) Send the input sealed to the seller's key; receive the encrypted result + invoice.
            sealed = crypto_utils.seal(commit.seller_pubkey_b64, text.encode("utf-8"), context=job_id)
            try:
                res = await self.registry.seller_job(url, schemas.SellerJobRequest(job_id=job_id, sealed_input=sealed))
            except RegistryError as e:
                raise FlowError(f"Seller could not complete the job: {e.detail}") from e

            # 4) Check everything against what the seller committed at the registry.
            job = await self.registry.get_job(job_id)
            _verify_delivery(job, res, price)

            # 5) Pay.
            inv = bolt11.decode(res.bolt11)
            if inv.demo:
                if not self.wallet.demo_mode:
                    raise FlowError("Seller issued a DEMO invoice but this buyer expects real Lightning")
                pay = await self.registry.seller_demo_pay(url, schemas.DemoPayRequest(payment_hash=res.payment_hash,
                                                                                     amount_sats=price))
                preimage: Optional[str] = pay.preimage_hex
            else:
                try:
                    pay_r = await self.wallet.pay_invoice(res.bolt11, expected_amount_sats=price,
                                                          expected_payment_hash=res.payment_hash, max_amount_sats=ticket.budget_sats)
                except PaymentRefused as e:
                    raise FlowError(f"Payment refused: {e}") from e
                preimage = pay_r.get("preimage")
            paid = True
            await self.budget.commit(price)
        finally:
            if not paid:
                await self.budget.release(price)

        if preimage and not crypto_utils.preimage_matches(preimage, res.payment_hash):
            preimage = None  # never forward a bogus preimage

        # 6) Obtain the result key.
        key = await self._obtain_key(url, job_id, res, preimage)

        # 7) Report the payment (verified by preimage, or already by the seller's wallet).
        pay_ack = await self.registry.record_payment(job_id, ticket.token, schemas.JobPaymentRequest(
            seller_id=seller_id, amount_sats=price, mode=res.mode, lightning_payment_hash=res.payment_hash,
            lightning_preimage=preimage, bolt11=res.bolt11))

        # 8) Decrypt and verify; dispute on mismatch.
        plaintext: Optional[bytes] = None
        if key is not None and crypto_utils.key_commitment(key) == res.key_commitment:
            try:
                plaintext = crypto_utils.decrypt_with_key(key, res.result_ciphertext_b64, res.result_nonce_b64,
                                                          res.result_tag_b64, aad=job_id.encode())
            except Exception:  # noqa: BLE001
                plaintext = None
        if plaintext is None or crypto_utils.hash_result(plaintext) != res.result_hash:
            verdict = await self.registry.dispute(job_id, ticket.token, schemas.DisputeRequest(
                reason="result did not decrypt or did not match the committed hash",
                result_ciphertext_b64=res.result_ciphertext_b64, result_nonce_b64=res.result_nonce_b64,
                result_tag_b64=res.result_tag_b64, preimage_hex=preimage,
                key_b64=crypto_utils.b64e(key) if key else None))
            raise FlowError(f"Result failed verification after payment. Dispute upheld={verdict.upheld}: {verdict.detail}")

        # 9) Accept.
        await self.registry.settle(job_id, ticket.token)
        return JobResult(task_id=task_id, job_id=job_id, seller_id=seller_id, amount_sats=price,
                         payment_hash=res.payment_hash, mode=res.mode, result_hash=res.result_hash,
                         result_text=plaintext.decode("utf-8", errors="replace").strip(),
                         payment_verified_by=pay_ack.verified_by)

    async def _obtain_key(self, url: str, job_id: str, res: schemas.SellerJobResponse,
                          preimage: Optional[str]) -> Optional[bytes]:
        if res.key_release == constants.KEY_RELEASE_PREIMAGE:
            if not preimage:
                raise FlowError("Seller uses preimage key release but the wallet returned no preimage")
            return crypto_utils.derive_result_key(bytes.fromhex(preimage), job_id)
        l402 = f"{res.macaroon}:{preimage}" if (preimage and res.macaroon) else None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + KEY_POLL_SECONDS
        while True:
            try:
                kr = await self.registry.seller_key(url, schemas.SellerKeyRequest(
                    job_id=job_id, payment_hash=res.payment_hash, preimage_hex=preimage), l402=l402)
                return crypto_utils.b64d(kr.key_b64)
            except RegistryError as e:
                if e.status != 402 or loop.time() >= deadline:
                    logger.warning("Seller did not release the key: %s", e)
                    return None
                await asyncio.sleep(3.0)  # payment still propagating to the seller's wallet


def describe_input(text: str) -> dict:
    """Public description of the input used for quoting. Contains no content or hash of it."""
    return {"type": "string", "bytes": len(text.encode("utf-8")), "chars": len(text), "items": max(1, len([ln for ln in text.splitlines() if ln.strip()]))}


def _verify_delivery(job: schemas.JobSummary, res: schemas.SellerJobResponse, price: int) -> None:
    problems = []
    if job.status != constants.STATUS_DELIVERED:
        problems.append(f"registry status is {job.status}")
    if res.amount_sats != price or job.accepted_price_sats != price:
        problems.append(f"invoice amount {res.amount_sats} != agreed {price}")
    if job.payment_hash != res.payment_hash.lower():
        problems.append("invoice hash differs from the registry's")
    if job.bolt11 != res.bolt11:
        problems.append("invoice differs from the one reported to the registry")
    if job.result_hash != res.result_hash or job.key_commitment != res.key_commitment:
        problems.append("result/key commitments differ from the registry's")
    digest = crypto_utils.ciphertext_digest(res.result_ciphertext_b64, res.result_nonce_b64, res.result_tag_b64)
    if job.ciphertext_hash != digest:
        problems.append("ciphertext differs from the committed one")
    try:
        inv = bolt11.decode(res.bolt11)
        if inv.payment_hash != res.payment_hash.lower() or inv.amount_sat != price:
            problems.append("invoice contents do not match its reported hash/amount")
    except bolt11.InvoiceError as e:
        problems.append(f"invalid invoice: {e}")
    if problems:
        raise FlowError("Refusing to pay: " + "; ".join(problems))
