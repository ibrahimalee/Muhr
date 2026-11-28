/**
 * TypeScript interfaces matching backend Pydantic schemas from shared/schemas.py
 * These types ensure type safety for all API requests and responses.
 */

// ---- Seller Registration ----
export interface SellerRegisterRequest {
  lightning_pubkey: string;
  capability: string;
  price_sats_per_unit: number;
  unit_definition: string;
  endpoint_url: string;
  commitment_endpoint: string;
  docker_image_hash: string;
  stake_payment_hash?: string;
  optimal_input_schema?: Record<string, unknown>;
}

export interface SellerRegisterResponse {
  seller_id: string;
  status: string;
  stake_sats: number;
  stake_verified?: boolean;
  max_job_value: number;
  registered_at: string;
  /** Returned once; send as X-Muhr-Seller-Key on seller-only calls. */
  seller_key?: string;
}

// ---- Seller Discovery ----
export interface SellerInfo {
  seller_id: string;
  capability: string;
  price_sats_per_unit: number;
  unit_definition: string;
  jobs_completed: number;
  stake_sats: number;
  reputation_score: number;
  avg_response_ms: number;
  endpoint_url: string;
  status: string;
  last_seen: string | null;
  /** True when every job runs on a local model, so the input never reaches a hosted provider. */
  private?: boolean;
}

export interface SellerListResponse {
  sellers: SellerInfo[];
  total: number;
  generated_at: string;
}

// ---- Task Posting ----
export interface TaskPostRequest {
  task_id: string;
  capability_needed: string;
  input_schema: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  budget_sats: number;
  payment_hash: string;
  expiry_seconds?: number;
  buyer_pubkey: string;
}

export interface TaskPostResponse {
  task_id: string;
  status: string;
  matched_sellers: string[];
}

export interface DemoRunRequest {
  input_text: string;
  capability?: string;
  budget_sats?: number;
  seller_id?: string;
}

export interface DemoHealthResponse {
  registry: string;
  summarizer_url: string;
  summarizer_ok: boolean;
  summarizer_status?: number;
  summarizer_body?: string;
  detail?: string;
}

export interface DemoRunResponse {
  ok: boolean;
  task_id: string;
  job_id: string;
  seller_id: string;
  capability: string;
  budget_sats: number;
  payment_hash: string;
  lightning_payment_hash: string;
  lightning_mode: "REAL" | "DEMO" | string;
  result_hash: string;
  result_text: string;
  result_preview: string;
}

// ---- Commitment ----
export interface CommitmentRequest {
  seller_id: string;
  computation_hash: string;
  accepted_price_sats: number;
  estimated_completion_ms?: number;
}

export interface CommitmentResponse {
  commitment_accepted: boolean;
  job_id: string;
  data_can_be_sent: boolean;
}

// ---- Job Completion ----
export interface JobCompleteRequest {
  seller_id: string;
  result_hash: string;
  result_url: string;
}

export interface JobCompleteResponse {
  verified: boolean;
  payment_status: string;
}

// ---- Seller-side endpoints ----
export interface SellerCommitRequest {
  task_id: string;
  input_schema: Record<string, unknown>;
  budget_sats: number;
}

export interface SellerCommitResponse {
  computation_hash: string;
  accepted: boolean;
  estimated_ms: number;
}

export interface SellerJobRequest {
  job_id: string;
  ciphertext_b64: string;
  nonce_b64: string;
  tag_b64: string;
  preimage_b64?: string;
}

export interface SellerJobResponse {
  job_id: string;
  result_b64: string;
  result_hash: string;
}

// ---- SSE Feed Event ----
export interface FeedEvent {
  type: string;
  timestamp: string;
  job_id?: string;
  task_id?: string;
  seller_id?: string;
  capability?: string;
  amount_sats?: number;
  detail?: string;
  lightning_payment_hash?: string;
  lightning_mode?: "REAL" | "DEMO" | string;
}

// ---- Human Approval ----
export interface ApprovalRequest {
  request_id: string;
  reason: string;
  amount_sats: number;
  task_description: string;
}

export interface ApprovalResponse {
  request_id: string;
  approved: boolean;
}

/** GET /api/stats (registry) */
export interface MarketStats {
  settled_jobs: number;
  active_sellers: number;
  net_to_sellers_sats: number;
  platform_fees_sats: number;
  gross_job_volume_sats: number;
  real_volume_sats?: number;
  demo_volume_sats?: number;
  transaction_count: number;
  demo_mode?: boolean;
  generated_at: string;
}

/** GET /api/jobs */
export interface JobSummary {
  job_id: string;
  task_id: string;
  seller_id: string;
  capability: string;
  budget_sats: number;
  accepted_price_sats?: number | null;
  status: string;
  payment_hash: string;
  computation_hash: string | null;
  result_hash: string | null;
  key_commitment?: string | null;
  ciphertext_hash?: string | null;
  /** "preimage" (key derived from the payment preimage) or "seller_confirmed". */
  key_release?: string | null;
  bolt11?: string | null;
  payment_verified?: boolean;
  created_at: string;
  committed_at: string | null;
  delivered_at: string | null;
  settled_at: string | null;
  lightning_payment_hash?: string | null;
  lightning_mode?: "REAL" | "DEMO" | string | null;
}

/** GET /api/buyer/wallet (registry proxy to MDK) */
export interface BuyerWalletStatus {
  available: boolean;
  mode: "REAL" | "DEMO" | string;
  balance_sats: number;
  network?: string | null;
  pubkey?: string | null;
  detail?: string | null;
  generated_at: string;
}

export interface JobListResponse {
  jobs: JobSummary[];
  total: number;
  generated_at: string;
}

/** GET /api/jobs/{id}/receipt: public fields only (no keys, tokens or content). */
export interface ReceiptResponse {
  job_id: string;
  seller_id: string;
  capability: string;
  price_sats: number;
  platform_fee_sats: number;
  payment_hash: string;
  /** Present only for preimage key release when the registry already holds it. */
  preimage: string | null;
  result_hash: string | null;
  key_commitment: string | null;
  ciphertext_hash: string | null;
  mode: "REAL" | "DEMO" | string;
  key_release: string | null;
  payment_verified_by: string | null;
  settled_at: string;
  dispute: "none" | "upheld" | string;
}
