import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiClient, APIError, NetworkError } from './api-client';
import { API_CONFIG } from '@/config/api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('APIError', () => {
  it('should create APIError with status code and message', () => {
    const error = new APIError(404, 'Not found');
    expect(error.name).toBe('APIError');
    expect(error.statusCode).toBe(404);
    expect(error.message).toBe('Not found');
  });

  it('should include response data', () => {
    const responseData = { detail: 'Resource not found' };
    const error = new APIError(404, 'Not found', responseData);
    expect(error.response).toEqual(responseData);
  });
});

describe('NetworkError', () => {
  it('should create NetworkError with message', () => {
    const error = new NetworkError('Connection failed');
    expect(error.name).toBe('NetworkError');
    expect(error.message).toBe('Connection failed');
  });
});

describe('apiClient', () => {
  beforeEach(() => {
    mockFetch.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe('get', () => {
    it('should make GET request with correct URL', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: 'test' }),
      });

      const result = await apiClient.get('/api/test');

      expect(mockFetch).toHaveBeenCalledWith(
        `${API_CONFIG.BASE_URL}/api/test`,
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );
      expect(result).toEqual({ data: 'test' });
    });

    it('should append query parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: 'test' }),
      });

      await apiClient.get('/api/test', { foo: 'bar', baz: 'qux' });

      const calledUrl = mockFetch.mock.calls[0][0];
      expect(calledUrl).toContain('foo=bar');
      expect(calledUrl).toContain('baz=qux');
    });

    it('should throw NetworkError on network failure', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      const promise = apiClient.get('/api/test');
      const assertion = expect(promise).rejects.toThrow(NetworkError);
      
      // Advance through all retry attempts
      for (let i = 0; i < API_CONFIG.RETRY_ATTEMPTS; i++) {
        await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY * Math.pow(2, i));
      }

      await assertion;
    });

    it('should throw APIError on HTTP error', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Not found' }),
      });

      const promise = apiClient.get('/api/test');
      const assertion = expect(promise).rejects.toThrow('Not found');
      
      // Advance through all retry attempts (APIError with 4xx should not retry, but we need to let the promise resolve)
      await vi.advanceTimersByTimeAsync(0);

      await assertion;
    });
  });

  describe('post', () => {
    it('should make POST request with body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const data = { name: 'test' };
      const result = await apiClient.post('/api/test', data);

      expect(mockFetch).toHaveBeenCalledWith(
        `${API_CONFIG.BASE_URL}/api/test`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(data),
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );
      expect(result).toEqual({ success: true });
    });

    it('should never retry a POST (non-idempotent), even on 5xx', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => ({ detail: 'Demo E2E failed' }),
      });

      const assertion = expect(apiClient.post('/api/demo/run_e2e', {})).rejects.toThrow('Demo E2E failed');
      await vi.advanceTimersByTimeAsync(10_000);
      await assertion;
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('should turn a structured FastAPI detail into readable text', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 402,
        json: async () => ({ detail: { error: 'payment_required' } }),
      });

      await expect(apiClient.post('/api/test', {})).rejects.toThrow('{"error":"payment_required"}');
    });
  });

  describe('put', () => {
    it('should make PUT request with body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ updated: true }),
      });

      const data = { name: 'updated' };
      const result = await apiClient.put('/api/test', data);

      expect(mockFetch).toHaveBeenCalledWith(
        `${API_CONFIG.BASE_URL}/api/test`,
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual({ updated: true });
    });
  });

  describe('delete', () => {
    it('should make DELETE request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ deleted: true }),
      });

      const result = await apiClient.delete('/api/test');

      expect(mockFetch).toHaveBeenCalledWith(
        `${API_CONFIG.BASE_URL}/api/test`,
        expect.objectContaining({
          method: 'DELETE',
        })
      );
      expect(result).toEqual({ deleted: true });
    });
  });

  describe('timeout handling', () => {
    it('should timeout after configured duration', async () => {
      mockFetch.mockImplementation(() => 
        new Promise(() => {
          // This promise will never resolve naturally
        })
      );

      const promise = apiClient.get('/api/test');
      const assertion = expect(promise).rejects.toThrow('Request timeout');
      
      // Each timeout is retried by the client; execute the complete retry schedule.
      await vi.runAllTimersAsync();
      
      await assertion;
    });
  });

  describe('retry logic', () => {
    it('should retry on network error with exponential backoff', async () => {
      // Fail first 2 attempts, succeed on 3rd
      mockFetch
        .mockRejectedValueOnce(new Error('Network error'))
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ data: 'success' }),
        });

      const promise = apiClient.get('/api/test');

      // First attempt fails immediately
      await vi.advanceTimersByTimeAsync(0);
      
      // Wait for first retry delay (1000ms)
      await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY);
      
      // Wait for second retry delay (2000ms - exponential backoff)
      await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY * 2);

      const result = await promise;
      expect(result).toEqual({ data: 'success' });
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    it('should not retry on 4xx errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Bad request' }),
      });

      await expect(apiClient.get('/api/test')).rejects.toThrow(APIError);
      expect(mockFetch).toHaveBeenCalledTimes(1); // No retries
    });

    it('should retry on 5xx errors', async () => {
      // Fail with 500, then succeed
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Server error' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ data: 'success' }),
        });

      const promise = apiClient.get('/api/test');
      
      // Wait for retry delay
      await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY);

      const result = await promise;
      expect(result).toEqual({ data: 'success' });
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it('should throw after max retries', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      const promise = apiClient.get('/api/test');
      const assertion = expect(promise).rejects.toThrow(NetworkError);

      // Advance through all retry attempts
      for (let i = 0; i < API_CONFIG.RETRY_ATTEMPTS; i++) {
        await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY * Math.pow(2, i));
      }

      await assertion;
      expect(mockFetch).toHaveBeenCalledTimes(API_CONFIG.RETRY_ATTEMPTS);
    });
  });

  describe('error response handling', () => {
    it('should parse error detail from response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Validation error' }),
      });

      try {
        await apiClient.get('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(APIError);
        expect((error as APIError).statusCode).toBe(422);
        expect((error as APIError).message).toBe('Validation error');
      }
    });

    it('should handle response without detail field', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      });

      const promise = apiClient.get('/api/test');
      const outcome = promise.then(
        () => new Error('Expected request to fail'),
        (error) => error,
      );
      
      // Advance through retry attempts for 5xx error
      for (let i = 0; i < API_CONFIG.RETRY_ATTEMPTS; i++) {
        await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY * Math.pow(2, i));
      }

      const error = await outcome;
      expect(error).toBeInstanceOf(APIError);
      expect((error as APIError).message).toBe('HTTP 500');
    });

    it('should handle response with invalid JSON', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      });

      const promise = apiClient.get('/api/test');
      const outcome = promise.then(
        () => new Error('Expected request to fail'),
        (error) => error,
      );
      
      // Advance through retry attempts for 5xx error
      for (let i = 0; i < API_CONFIG.RETRY_ATTEMPTS; i++) {
        await vi.advanceTimersByTimeAsync(API_CONFIG.RETRY_DELAY * Math.pow(2, i));
      }

      const error = await outcome;
      expect(error).toBeInstanceOf(APIError);
      expect((error as APIError).statusCode).toBe(500);
    });
  });
});
