/**
 * API configuration and endpoint constants
 * Provides centralized configuration for backend communication
 */

// Type-safe access to Vite environment variables
const getEnvVar = (key: string): string | undefined => {
  return (import.meta as any).env?.[key];
};

export const API_CONFIG = {
  /** Empty string = same origin (use Vite `server.proxy` in dev). Set full URL in production. */
  BASE_URL: (getEnvVar("VITE_API_BASE_URL") ?? "").replace(/\/+$/, "") || "",
  /** Default fetch budget; local MDK / SQLite / Windows can exceed 10s in dev. */
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000, // 1 second
} as const;

export const API_ENDPOINTS = {
  SELLERS: '/api/sellers',
  SELLERS_REGISTER: '/api/sellers/register',
  JOBS: '/api/jobs',
  STATS: '/api/stats',
  RATES: '/api/rates',
  JOB_RECEIPT: (jobId: string) => `/api/jobs/${jobId}/receipt`,
  TASKS: '/api/tasks',
  DEMO_RUN_E2E: '/api/demo/run_e2e',
  DEMO_HEALTH: '/api/demo/health',
  JOBS_COMMITMENT: (taskId: string) => `/api/jobs/${taskId}/commitment`,
  JOBS_COMPLETE: (jobId: string) => `/api/jobs/${jobId}/complete`,
  JOBS_SETTLE: (jobId: string) => `/api/jobs/${jobId}/settle`,
  JOBS_HTLC_OPENED: (jobId: string) => `/api/jobs/${jobId}/htlc_opened`,
  JOBS_DATA_SENT: (jobId: string) => `/api/jobs/${jobId}/data_sent`,
  FEED: '/api/feed',
  APPROVE: '/api/approve',
  APPROVE_STATUS: (requestId: string) => `/api/approve/${requestId}`,
  HEALTH: '/health',
  BUYER_WALLET: '/api/buyer/wallet',
  JOBS_PAYMENT: (jobId: string) => `/api/jobs/${jobId}/payment`,
  SELLER_STAKE: (sellerId: string) => `/api/sellers/${sellerId}/stake`,
  SELLER_UNSTAKE: (sellerId: string) => `/api/sellers/${sellerId}/unstake`,
} as const;
