"""All API request/response models shared by registry, sellers and buyer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, Field, PlainSerializer


def _iso_utc(d: datetime) -> str:
    """Serialize datetimes as explicit UTC (DB rows are naive UTC)."""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str, when_used="json")]

Hex64 = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]
Capability = Annotated[str, Field(pattern=r"^[a-z0-9_]{2,64}$")]


# ---- Seller Registration ----
class SellerRegisterRequest(BaseModel):
    lightning_pubkey: Annotated[str, Field(min_length=1, max_length=66)]
    capability: Capability
    price_sats_per_unit: Annotated[int, Field(ge=0, le=10_000_000)]
    unit_definition: Annotated[str, Field(min_length=1, max_length=200)]
    endpoint_url: Annotated[str, Field(max_length=500)]
    commitment_endpoint: Annotated[str, Field(max_length=500)]
    docker_image_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    stake_payment_hash: Optional[str] = None
    optimal_input_schema: Optional[dict] = None


class SellerRegisterResponse(BaseModel):
    seller_id: str
    status: str
    stake_sats: int
    stake_verified: bool
    max_job_value: int
    registered_at: UtcDatetime
    # Returned exactly once. Send it as X-Muhr-Seller-Key on seller-only calls.
    seller_key: str


# ---- Seller Discovery ----
class SellerInfo(BaseModel):
    seller_id: str
    capability: str
    price_sats_per_unit: int
    unit_definition: str
    jobs_completed: int
    jobs_failed: int = 0
    stake_sats: int
    reputation_score: float
    avg_response_ms: int
    endpoint_url: str
    status: str
    last_seen: Optional[UtcDatetime] = None


class SellerListResponse(BaseModel):
    sellers: list[SellerInfo]
    total: int
    generated_at: UtcDatetime


# ---- Task Posting ----
class TaskPostRequest(BaseModel):
    task_id: Optional[Annotated[str, Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$")]] = None
    capability_needed: Capability
    input_schema: dict = Field(default_factory=dict)
    output_schema: Optional[dict] = None
    budget_sats: Annotated[int, Field(ge=1, le=10_000_000)]
    expiry_seconds: Annotated[int, Field(ge=10, le=86_400)] = 300
    buyer_pubkey: Annotated[str, Field(min_length=1, max_length=200)]
    # Unused field kept for compatibility; ignored (the lock is the seller's invoice hash).
    payment_hash: Optional[str] = None


class TaskPostResponse(BaseModel):
    task_id: str
    status: str
    matched_sellers: list[str]
    expires_at: UtcDatetime
    # Returned exactly once. Send it as X-Muhr-Buyer-Token on buyer-only calls.
    buyer_token: str


# ---- Commitment (seller -> registry) ----
class CommitmentRequest(BaseModel):
    seller_id: str
    computation_hash: Hex64
    accepted_price_sats: Annotated[int, Field(ge=1)]
    estimated_completion_ms: int = 5000


class CommitmentResponse(BaseModel):
    commitment_accepted: bool
    job_id: str
    data_can_be_sent: bool


# ---- Seller /commit (buyer -> seller) ----
class SellerCommitRequest(BaseModel):
    task_id: str
    input_schema: dict = Field(default_factory=dict)
    budget_sats: int


class SellerCommitResponse(BaseModel):
    computation_hash: str
    accepted: bool
    estimated_ms: int
    job_id: Optional[str] = None
    price_sats: Optional[int] = None
    seller_id: Optional[str] = None
    # X25519 public key the buyer seals its input to.
    seller_pubkey_b64: Optional[str] = None


# ---- Seller /job (buyer -> seller) ----
class SealedPayload(BaseModel):
    ephemeral_pub_b64: str
    ciphertext_b64: str
    nonce_b64: str
    tag_b64: str


class SellerJobRequest(BaseModel):
    job_id: str
    sealed_input: SealedPayload


class SellerJobResponse(BaseModel):
    job_id: str
    # Result encrypted under K; the buyer obtains K by paying.
    result_ciphertext_b64: str
    result_nonce_b64: str
    result_tag_b64: str
    result_hash: str                 # sha256(plaintext result), committed to the registry
    key_commitment: str              # sha256(K), committed to the registry
    key_release: str                 # preimage | seller_confirmed
    bolt11: str
    payment_hash: str
    amount_sats: int
    mode: str                        # REAL | DEMO
    # L402 macaroon for /key: send "Authorization: L402 <macaroon>:<preimage_hex>".
    macaroon: Optional[str] = None


class SellerKeyRequest(BaseModel):
    job_id: str
    payment_hash: Hex64
    preimage_hex: Optional[str] = None


class SellerKeyResponse(BaseModel):
    job_id: str
    key_b64: str
    payment_confirmed_by: str        # preimage | seller_wallet


class DemoPayRequest(BaseModel):
    payment_hash: Hex64
    amount_sats: int


class DemoPayResponse(BaseModel):
    payment_hash: str
    preimage_hex: str
    mode: str = "DEMO"


# ---- Seller -> registry lifecycle ----
class JobReceivedRequest(BaseModel):
    seller_id: str


class JobCompleteRequest(BaseModel):
    seller_id: str
    result_hash: Hex64
    invoice_payment_hash: Hex64
    bolt11: Annotated[str, Field(min_length=1, max_length=2000)]
    amount_sats: Annotated[int, Field(ge=1)]
    key_commitment: Hex64
    ciphertext_hash: Hex64           # sha256 over the encrypted result (dispute evidence binding)
    key_release: str
    # Runtime-attested pipeline hash; mismatch with the committed one => 100% slash.
    seller_committed_hash: Optional[Hex64] = None
    lightning_mode: str = "DEMO"


class JobCompleteResponse(BaseModel):
    verified: bool
    payment_status: str
    slashed: bool = False
    slash_reason: Optional[str] = None


class JobFailRequest(BaseModel):
    seller_id: str
    reason: Annotated[str, Field(max_length=500)]


class PaymentConfirmRequest(BaseModel):
    seller_id: str
    payment_hash: Hex64


# ---- Buyer -> registry payment / settle / dispute ----
class JobPaymentRequest(BaseModel):
    seller_id: str
    amount_sats: Annotated[int, Field(ge=1)]
    mode: str = "DEMO"  # REAL | DEMO
    lightning_payment_hash: Hex64
    lightning_preimage: Optional[str] = None
    bolt11: Optional[str] = None


class JobPaymentResponse(BaseModel):
    recorded: bool
    tx_id: str
    mode: str
    verified: bool
    verified_by: Optional[str] = None


class DisputeRequest(BaseModel):
    reason: Annotated[str, Field(max_length=500)]
    result_ciphertext_b64: str
    result_nonce_b64: str
    result_tag_b64: str
    preimage_hex: Optional[str] = None
    key_b64: Optional[str] = None


class DisputeResponse(BaseModel):
    upheld: bool
    detail: str
    slashed_sats: int = 0


# ---- Demo ----
class DemoRunRequest(BaseModel):
    input_text: Annotated[str, Field(max_length=50_000)]
    capability: Optional[str] = None
    budget_sats: Annotated[int, Field(ge=1, le=10_000)] = 100
    seller_id: str = "sel_summarizer"


class DemoRunResponse(BaseModel):
    ok: bool
    task_id: str
    job_id: str
    seller_id: str
    capability: str
    budget_sats: int
    payment_hash: str
    lightning_payment_hash: str
    lightning_mode: str
    result_hash: str
    result_text: str
    result_preview: str


# ---- Stake ----
class StakeDepositRequest(BaseModel):
    amount_sats: Annotated[int, Field(ge=1, le=100_000_000)]
    payment_hash: Hex64


class StakeDepositResponse(BaseModel):
    seller_id: str
    new_stake_sats: int
    new_max_job_value: int
    stake_id: str
    status: str


class StakeWithdrawRequest(BaseModel):
    reason: Optional[str] = None


class StakeWithdrawResponse(BaseModel):
    seller_id: str
    withdrawn_sats: int
    new_status: str


# ---- Jobs ----
class JobSummary(BaseModel):
    job_id: str
    task_id: str
    seller_id: str
    capability: str
    budget_sats: int
    accepted_price_sats: Optional[int] = None
    status: str
    payment_hash: str
    computation_hash: Optional[str] = None
    result_hash: Optional[str] = None
    key_commitment: Optional[str] = None
    ciphertext_hash: Optional[str] = None
    key_release: Optional[str] = None
    bolt11: Optional[str] = None
    lightning_payment_hash: Optional[str] = None
    lightning_mode: Optional[str] = None
    payment_verified: bool = False
    created_at: UtcDatetime
    committed_at: Optional[UtcDatetime] = None
    delivered_at: Optional[UtcDatetime] = None
    settled_at: Optional[UtcDatetime] = None


class JobListResponse(BaseModel):
    jobs: list[JobSummary]
    total: int
    generated_at: UtcDatetime


class MarketStats(BaseModel):
    settled_jobs: int
    active_sellers: int
    net_to_sellers_sats: int
    platform_fees_sats: int          # accrued ledger entries, not collected on-network
    gross_job_volume_sats: int
    real_volume_sats: int = 0
    demo_volume_sats: int = 0
    transaction_count: int
    demo_mode: bool
    generated_at: UtcDatetime


# ---- SSE Feed Event ----
class FeedEvent(BaseModel):
    type: str
    timestamp: UtcDatetime
    job_id: Optional[str] = None
    task_id: Optional[str] = None
    seller_id: Optional[str] = None
    capability: Optional[str] = None
    amount_sats: Optional[int] = None
    detail: Optional[str] = None
    lightning_payment_hash: Optional[str] = None
    lightning_mode: Optional[str] = None


# ---- Human Approval ----
class ApprovalRequest(BaseModel):
    request_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$")]
    reason: Annotated[str, Field(max_length=500)]
    amount_sats: Annotated[int, Field(ge=0)]
    task_description: Annotated[str, Field(max_length=2000)]


class ApprovalResponse(BaseModel):
    """Operator decision (POST /api/approve with admin key)."""
    request_id: str
    approved: bool


class ApprovalStatusResponse(BaseModel):
    request_id: str
    status: str                       # pending | approved | rejected
    approved: Optional[bool] = None   # None while pending
