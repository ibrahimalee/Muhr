# ===== MUHR SHARED CONSTANTS =====
#
# Everything that more than one component (registry, sellers, buyer MCP, scripts)
# needs to agree on lives here. Runtime flags are exposed as *functions* so that
# tests and long-running processes always see the current environment.

import os


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable ("1/true/yes/y/on")."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _base_url(env_key: str, default: str) -> str:
    """Read a base URL from the environment, or use default. Strips trailing slashes."""
    v = os.getenv(env_key, "").strip()
    return (v if v else default).rstrip("/")


def demo_mode() -> bool:
    """Single source of truth for DEMO_MODE across every component.

    Defaults to **true**: in DEMO mode no sats move on Lightning (invoices are
    synthetic). Set DEMO_MODE=false explicitly to use the MDK wallet.
    """
    return env_flag("DEMO_MODE", True)


def registry_base_url() -> str:
    return _base_url("MUHR_REGISTRY_BASE_URL", "http://127.0.0.1:8000")


def registry_internal_url() -> str:
    """URL the registry uses to call *itself* (live demo). Never derived from request headers."""
    return _base_url("MUHR_REGISTRY_INTERNAL_URL", registry_base_url())


def seller_summarizer_url() -> str:
    return _base_url("MUHR_SELLER_SUMMARIZER_URL", "http://127.0.0.1:8001")


def seller_classifier_url() -> str:
    return _base_url("MUHR_SELLER_CLASSIFIER_URL", "http://127.0.0.1:8002")


# Import-time snapshots kept for scripts that read them once.
REGISTRY_BASE_URL = registry_base_url()
MUHR_NEXUS_URL = _base_url("MUHR_NEXUS_URL", "http://127.0.0.1:8080")
DASHBOARD_URL = MUHR_NEXUS_URL
SELLER_SUMMARIZER_URL = seller_summarizer_url()
SELLER_CLASSIFIER_URL = seller_classifier_url()
DEMO_MODE = demo_mode()

# --- Pinned MDK wallet CLI (never @latest: it runs with access to wallet secrets) ---
MDK_AGENT_WALLET_PACKAGE_DEFAULT = "@moneydevkit/agent-wallet@0.22.0"


def mdk_package() -> str:
    return os.getenv("MDK_AGENT_WALLET_PACKAGE", MDK_AGENT_WALLET_PACKAGE_DEFAULT).strip()


# --- Auth headers ---
HEADER_SELLER_KEY = "X-Muhr-Seller-Key"
HEADER_BUYER_TOKEN = "X-Muhr-Buyer-Token"
HEADER_ADMIN_KEY = "X-Muhr-Admin-Key"

# --- API Paths ---
API_SELLERS = "/api/sellers"
API_SELLERS_REGISTER = "/api/sellers/register"
API_TASKS = "/api/tasks"
API_JOB = "/api/jobs/{job_id}"                            # GET detail
API_JOB_COMMITMENT = "/api/jobs/{task_id}/commitment"     # POST (seller)
API_JOB_RECEIVED = "/api/jobs/{job_id}/received"          # POST (seller)
API_JOB_COMPLETE = "/api/jobs/{job_id}/complete"          # POST (seller)
API_JOB_FAIL = "/api/jobs/{job_id}/fail"                  # POST (seller)
API_JOB_PAYMENT = "/api/jobs/{job_id}/payment"            # POST (buyer)
API_JOB_PAYMENT_CONFIRM = "/api/jobs/{job_id}/payment/confirm"  # POST (seller)
API_JOB_SETTLE = "/api/jobs/{job_id}/settle"              # POST (buyer)
API_JOB_DISPUTE = "/api/jobs/{job_id}/dispute"            # POST (buyer)
API_FEED = "/api/feed"                                    # GET SSE
API_JOBS = "/api/jobs"                                    # GET list
API_APPROVE = "/api/approve"                              # GET/POST
API_BUYER_WALLET = "/api/buyer/wallet"
API_SELLER_STAKE = "/api/sellers/{seller_id}/stake"
API_SELLER_UNSTAKE = "/api/sellers/{seller_id}/unstake"

# Seller-side endpoints
API_SELLER_HEALTH = "/health"
API_SELLER_COMMIT = "/commit"
API_SELLER_JOB = "/job"
API_SELLER_KEY = "/key"
API_SELLER_DEMO_PAY = "/demo/pay"   # DEMO only: simulates the network revealing the preimage

# --- Economic Constants ---
PLATFORM_FEE_PERCENT = 2
MIN_STAKE_SATS = 500
STAKE_TO_MAX_JOB_RATIO = 10          # max_job = stake / this
SLASH_WRONG_RESULT_PERCENT = 50
SLASH_TIMEOUT_PERCENT = 10
SLASH_CONTAINER_MISMATCH_PERCENT = 100

# --- Timing ---
HTLC_TIMEOUT_SECONDS = 60             # buyer must send data within this after commitment
JOB_DELIVERY_TIMEOUT_SECONDS = 180    # seller must deliver within this after acknowledging receipt
PAYMENT_TIMEOUT_SECONDS = 600         # buyer must pay a delivered invoice within this
AUTO_SETTLE_AFTER_SECONDS = 300       # paid-but-unsettled jobs settle automatically
SWEEPER_INTERVAL_SECONDS = 15
HEALTH_CHECK_INTERVAL_SECONDS = 300
HEALTH_CHECK_TIMEOUT_SECONDS = 5
MAX_CONSECUTIVE_FAILURES = 2

# --- Budget ---
DEFAULT_DAILY_BUDGET_SATS = 10000

# --- Seller Defaults (for cold start) ---
SUMMARIZER_CAPABILITY = "text_summarization"
SUMMARIZER_PRICE_PER_UNIT = 10
SUMMARIZER_UNIT = "per 1000 tokens"
SUMMARIZER_STAKE = 10000

CLASSIFIER_CAPABILITY = "data_classification"
CLASSIFIER_PRICE_PER_UNIT = 5
CLASSIFIER_UNIT = "per 100 items"
CLASSIFIER_STAKE = 10000

DEFAULT_DEMO_STAKE_SATS = 10000

# --- Job Statuses ---
STATUS_PENDING = "pending"
STATUS_COMMITTED = "committed"
STATUS_DATA_SENT = "data_sent"
STATUS_DELIVERED = "delivered"
STATUS_SETTLED = "settled"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"

# --- Task Statuses ---
TASK_OPEN = "open"
TASK_ASSIGNED = "assigned"
TASK_DONE = "done"
TASK_EXPIRED = "expired"

# --- Seller Statuses ---
SELLER_ACTIVE = "active"
SELLER_INACTIVE = "inactive"
SELLER_SUSPENDED = "suspended"

# --- Key release modes (how the buyer obtains the result decryption key) ---
KEY_RELEASE_PREIMAGE = "preimage"              # key = HKDF(payment preimage)
KEY_RELEASE_SELLER_CONFIRMED = "seller_confirmed"  # seller releases key after its wallet sees the payment

# --- SSE Event Types ---
EVENT_TASK_POSTED = "task_posted"
EVENT_COMMITMENT = "commitment"
EVENT_HTLC_OPENED = "htlc_opened"            # invoice issued, payment locked to its hash
EVENT_DATA_SENT = "data_sent"
EVENT_RESULT_DELIVERED = "result_delivered"
EVENT_PAYMENT_SETTLED = "payment_settled"
EVENT_LIGHTNING_PAID = "lightning_paid"
EVENT_REPUTATION_UPDATED = "reputation_updated"
EVENT_STAKE_SLASHED = "stake_slashed"
EVENT_STAKE_DEPOSITED = "stake_deposited"
EVENT_STAKE_WITHDRAWN = "stake_withdrawn"
EVENT_JOB_FAILED = "job_failed"
EVENT_JOB_TIMEOUT = "job_timeout"
EVENT_DISPUTE = "dispute"
EVENT_APPROVAL_REQUESTED = "approval_requested"
EVENT_APPROVAL_DECIDED = "approval_decided"
