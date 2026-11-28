import { API_CONFIG, API_ENDPOINTS } from "@/config/api";
import { APIError, apiClient, NetworkError } from "@/lib/api-client";
import type { Rates } from "@/lib/pkr";
import type {
  BuyerWalletStatus,
  DemoHealthResponse,
  DemoRunRequest,
  DemoRunResponse,
  FeedEvent,
  JobListResponse,
  MarketStats,
  ReceiptResponse,
  SellerListResponse,
  TaskPostRequest,
  TaskPostResponse,
} from "@/types/api";

export class MuhrApiError extends Error {
  constructor(message: string, public readonly statusCode?: number) {
    super(message);
    this.name = "MuhrApiError";
  }
}

type HealthResponse = { status: string; timestamp: string };

function toMuhrError(error: unknown): MuhrApiError {
  if (error instanceof MuhrApiError) return error;
  if (error instanceof APIError) return new MuhrApiError(error.message, error.statusCode);
  if (error instanceof NetworkError) return new MuhrApiError(error.message);
  return new MuhrApiError(error instanceof Error ? error.message : "Registry request failed");
}

export async function getHealth(): Promise<HealthResponse> {
  try {
    return await apiClient.get<HealthResponse>(API_ENDPOINTS.HEALTH);
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function getSellers(): Promise<SellerListResponse> {
  try {
    return await apiClient.get<SellerListResponse>(API_ENDPOINTS.SELLERS);
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function getStats(): Promise<MarketStats> {
  try {
    return await apiClient.get<MarketStats>(API_ENDPOINTS.STATS);
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function getJobs(limit: number): Promise<JobListResponse> {
  try {
    return await apiClient.get<JobListResponse>(API_ENDPOINTS.JOBS, {
      limit: String(Math.max(1, Math.min(500, Math.floor(limit)))),
    });
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function getRates(): Promise<Rates> {
  try {
    return await apiClient.get<Rates>(API_ENDPOINTS.RATES);
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function getReceipt(jobId: string): Promise<ReceiptResponse> {
  try {
    return await apiClient.get<ReceiptResponse>(API_ENDPOINTS.JOB_RECEIPT(jobId));
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function getBuyerWallet(): Promise<BuyerWalletStatus> {
  try {
    return await apiClient.get<BuyerWalletStatus>(API_ENDPOINTS.BUYER_WALLET);
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function postTask(task: TaskPostRequest): Promise<TaskPostResponse> {
  try {
    return await apiClient.post<TaskPostResponse>(API_ENDPOINTS.TASKS, task);
  } catch (error) {
    throw toMuhrError(error);
  }
}

/** The live demo calls a real LLM and settles a job; allow it several minutes. */
const DEMO_RUN_TIMEOUT_MS = 180_000;

export async function getDemoHealth(): Promise<DemoHealthResponse> {
  try {
    return await apiClient.get<DemoHealthResponse>(API_ENDPOINTS.DEMO_HEALTH);
  } catch (error) {
    throw toMuhrError(error);
  }
}

export async function runDemoE2E(request: DemoRunRequest): Promise<DemoRunResponse> {
  try {
    return await apiClient.post<DemoRunResponse>(API_ENDPOINTS.DEMO_RUN_E2E, request, {
      timeout: DEMO_RUN_TIMEOUT_MS,
    });
  } catch (error) {
    throw toMuhrError(error);
  }
}

/** Human-readable error text for toasts and inline banners. */
export function formatApiError(error: unknown, opts: { ifAbort?: "longDemo" } = {}): string {
  const message = error instanceof Error ? error.message : String(error ?? "Unknown error");
  if (opts.ifAbort === "longDemo" && /timeout|abort/i.test(message)) {
    return "The live demo took longer than 3 minutes. The seller's LLM may be slow or down; check /api/demo/health and the seller logs.";
  }
  if (error instanceof MuhrApiError && error.statusCode) {
    return `HTTP ${error.statusCode}: ${message}`;
  }
  return message;
}

export function getFeedEventSourceUrl(): string {
  return `${API_CONFIG.BASE_URL}${API_ENDPOINTS.FEED}`;
}

export function mapFeedEventToTerminalRow(event: FeedEvent, index: number) {
  const timestamp = new Date(event.timestamp);
  const time = Number.isNaN(timestamp.getTime())
    ? "--:--:--"
    : timestamp.toLocaleTimeString([], { hour12: false });
  const id = event.job_id ?? event.task_id ?? event.seller_id ?? "registry";
  return {
    t: time,
    hash: id.length > 18 ? `${id.slice(0, 18)}…` : id,
    msg: event.detail ?? event.type.replace(/_/g, " "),
    amt: event.amount_sats == null ? "—" : `${event.amount_sats.toLocaleString()} sats`,
    key: `${event.timestamp}:${event.type}:${id}:${index}`,
  };
}
