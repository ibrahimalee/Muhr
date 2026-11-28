import { API_CONFIG, API_ENDPOINTS } from '@/config/api';

/**
 * Custom error class for API errors (HTTP errors from backend)
 */
export class APIError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public response?: unknown
  ) {
    super(message);
    this.name = 'APIError';
  }
}

/**
 * Custom error class for network errors (backend offline/unreachable)
 */
export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}

/**
 * Fetch with timeout using AbortController
 * @param url - The URL to fetch
 * @param options - Fetch options
 * @param timeout - Timeout in milliseconds
 * @returns Promise<Response>
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeout: number = API_CONFIG.TIMEOUT
): Promise<Response> {
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      controller.abort();
      reject(new NetworkError('Request timeout'));
    }, timeout);
  });

  try {
    const request = fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
    return await Promise.race([request, timeoutPromise]);
  } catch (error) {
    if (error instanceof NetworkError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new NetworkError('Request timeout');
    }
    throw new NetworkError('Network request failed');
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

/**
 * Fetch with retry logic and exponential backoff
 * @param url - The URL to fetch
 * @param options - Fetch options
 * @param retries - Number of retry attempts
 * @returns Promise<Response>
 */
function errorMessage(errorData: unknown, status: number): string {
  const detail = (errorData as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (detail != null) {
    try {
      return JSON.stringify(detail);
    } catch {
      /* fall through */
    }
  }
  return `HTTP ${status}`;
}

async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  retries: number = API_CONFIG.RETRY_ATTEMPTS,
  timeout: number = API_CONFIG.TIMEOUT
): Promise<Response> {
  let lastError: Error | null = null;

  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetchWithTimeout(url, options, timeout);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new APIError(response.status, errorMessage(errorData, response.status), errorData);
      }
      
      return response;
    } catch (error) {
      lastError = error as Error;
      
      // Don't retry on 4xx errors (client errors)
      if (error instanceof APIError && error.statusCode >= 400 && error.statusCode < 500) {
        throw error;
      }
      
      // Wait before retrying (exponential backoff)
      if (i < retries - 1) {
        await new Promise(resolve => 
          setTimeout(resolve, API_CONFIG.RETRY_DELAY * Math.pow(2, i))
        );
      }
    }
  }

  throw lastError || new NetworkError('Request failed after retries');
}

/**
 * API client with typed methods for all HTTP verbs
 */
export const apiClient = {
  /**
   * GET request
   * @param endpoint - API endpoint path
   * @param params - Query parameters
   * @returns Promise<T>
   */
  async get<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    // `new URL('/api/...')` requires a base and throws in the browser when the
    // recommended same-origin Vite proxy is used (BASE_URL is intentionally
    // empty). Build a relative query string in that case.
    const query = new URLSearchParams(params).toString();
    const url = `${API_CONFIG.BASE_URL}${endpoint}${query ? `?${query}` : ''}`;
    const response = await fetchWithRetry(url);
    return response.json();
  },

  /**
   * POST request
   * @param endpoint - API endpoint path
   * @param data - Request body data
   * @returns Promise<T>
   */
  async post<T>(endpoint: string, data: unknown, opts: { timeout?: number } = {}): Promise<T> {
    // POST is not idempotent (e.g. /api/demo/run_e2e moves sats): never auto-retry.
    const response = await fetchWithRetry(
      `${API_CONFIG.BASE_URL}${endpoint}`,
      { method: 'POST', body: JSON.stringify(data) },
      1,
      opts.timeout ?? API_CONFIG.TIMEOUT,
    );
    return response.json();
  },

  /**
   * PUT request
   * @param endpoint - API endpoint path
   * @param data - Request body data
   * @returns Promise<T>
   */
  async put<T>(endpoint: string, data: unknown): Promise<T> {
    const response = await fetchWithRetry(
      `${API_CONFIG.BASE_URL}${endpoint}`,
      { method: 'PUT', body: JSON.stringify(data) },
      1,
    );
    return response.json();
  },

  /**
   * DELETE request
   * @param endpoint - API endpoint path
   * @returns Promise<T>
   */
  async delete<T>(endpoint: string): Promise<T> {
    const response = await fetchWithRetry(`${API_CONFIG.BASE_URL}${endpoint}`, { method: 'DELETE' }, 1);
    return response.json();
  },
};
