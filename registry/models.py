"""SQLAlchemy models for MUHR Registry."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow() -> datetime:
    """Naive UTC timestamp (what SQLite stores); serialized with an explicit Z."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SellerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    DATA_SENT = "data_sent"
    DELIVERED = "delivered"
    SETTLED = "settled"
    FAILED = "failed"
    TIMEOUT = "timeout"


class Seller(Base):
    __tablename__ = "sellers"

    seller_id = Column(String(64), primary_key=True)
    lightning_pubkey = Column(String(66), nullable=False, unique=True)
    capability = Column(String(100), nullable=False, index=True)
    price_sats_per_unit = Column(Integer, nullable=False)
    unit_definition = Column(String(200), nullable=False)
    endpoint_url = Column(String(500), nullable=False)
    commitment_endpoint = Column(String(500), nullable=False)
    docker_image_hash = Column(String(71), nullable=False)
    api_key_hash = Column(String(64), nullable=True)
    stake_sats = Column(Integer, nullable=False, default=0)
    stake_verified = Column(Boolean, nullable=False, default=False)
    max_job_value = Column(Integer, nullable=False, default=0)
    jobs_completed = Column(Integer, nullable=False, default=0)
    jobs_failed = Column(Integer, nullable=False, default=0)
    reputation_score = Column(Float, nullable=False, default=0.0)
    avg_response_ms = Column(Integer, nullable=False, default=0)
    status = Column(SQLEnum(SellerStatus), nullable=False, default=SellerStatus.ACTIVE, index=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_seen = Column(DateTime, nullable=True)
    registered_at = Column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        Index("idx_seller_capability_status", "capability", "status"),
        Index("idx_seller_status_stake", "status", "stake_sats"),
    )


class Task(Base):
    """A buyer's request. Persisted so a registry restart does not lose open work."""
    __tablename__ = "tasks"

    task_id = Column(String(64), primary_key=True)
    capability = Column(String(100), nullable=False, index=True)
    budget_sats = Column(Integer, nullable=False)
    input_schema = Column(JSON, nullable=True)
    buyer_pubkey = Column(String(200), nullable=False)
    buyer_token_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="open", index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String(64), primary_key=True)
    task_id = Column(String(64), nullable=False, index=True)
    seller_id = Column(String(64), ForeignKey("sellers.seller_id"), nullable=False, index=True)
    capability = Column(String(100), nullable=False)
    budget_sats = Column(Integer, nullable=False)
    accepted_price_sats = Column(Integer, nullable=True)
    # The Lightning lock: the seller's invoice payment hash (set on delivery).
    payment_hash = Column(String(64), nullable=False, default="")
    computation_hash = Column(String(64), nullable=True)
    seller_committed_hash = Column(String(64), nullable=True)
    result_hash = Column(String(64), nullable=True)
    key_commitment = Column(String(64), nullable=True)
    ciphertext_hash = Column(String(64), nullable=True)
    key_release = Column(String(32), nullable=True)
    bolt11 = Column(Text, nullable=True)
    lightning_payment_hash = Column(String(64), nullable=True)
    lightning_mode = Column(String(8), nullable=True)
    payment_verified = Column(Boolean, nullable=False, default=False)
    payment_verified_by = Column(String(32), nullable=True)
    failure_reason = Column(String(500), nullable=True)
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    committed_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    settled_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_job_seller_status", "seller_id", "status"),
        Index("idx_job_task", "task_id"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    tx_id = Column(String(64), primary_key=True)
    job_id = Column(String(64), ForeignKey("jobs.job_id"), nullable=True, index=True)
    seller_id = Column(String(64), ForeignKey("sellers.seller_id"), nullable=False, index=True)
    # stake_deposit | stake_withdrawal | stake_slash | payment | platform_fee
    type = Column(String(50), nullable=False)
    amount_sats = Column(Integer, nullable=False)
    mode = Column(String(8), nullable=True)  # REAL | DEMO for payments
    timestamp = Column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("idx_tx_seller_timestamp", "seller_id", "timestamp"),)


class Stake(Base):
    __tablename__ = "stakes"

    stake_id = Column(String(64), primary_key=True)
    seller_id = Column(String(64), ForeignKey("sellers.seller_id"), nullable=False, index=True)
    amount_sats = Column(Integer, nullable=False)
    payment_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="active")  # active | withdrawn
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Approval(Base):
    """Human-approval requests (budget overages). Persisted, operator-decided."""
    __tablename__ = "approvals"

    request_id = Column(String(64), primary_key=True)
    reason = Column(String(500), nullable=False)
    amount_sats = Column(Integer, nullable=False)
    task_description = Column(String(2000), nullable=False)
    status = Column(String(16), nullable=False, default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, nullable=False, default=utcnow)
    decided_at = Column(DateTime, nullable=True)
