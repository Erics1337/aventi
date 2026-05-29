import assert from 'node:assert/strict';
import test from 'node:test';

import { AventiApiClient, AventiApiError } from '../src/index.js';

const originalFetch = globalThis.fetch;

test.afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  });
}

function mockFetch(
  handler: (input: string | URL | Request, init?: RequestInit) => Response | Promise<Response>,
) {
  globalThis.fetch = handler as typeof fetch;
}

test('adds bearer auth for protected requests', async () => {
  let authorization: string | null = null;
  mockFetch((_input, init) => {
    authorization = new Headers(init?.headers).get('authorization');
    return jsonResponse({ id: 'user-1', email: null, preferences: {} });
  });

  const api = new AventiApiClient({
    baseUrl: 'https://api.example.test',
    getAccessToken: () => 'token-123',
  });

  await api.getMe();

  assert.equal(authorization, 'Bearer token-123');
});

test('rejects protected requests before fetch when no token is available', async () => {
  let fetchCalled = false;
  mockFetch(() => {
    fetchCalled = true;
    return jsonResponse({});
  });

  const api = new AventiApiClient({
    baseUrl: 'https://api.example.test',
    getAccessToken: () => null,
  });

  await assert.rejects(
    api.getMe(),
    (error) => {
      const apiError = error as AventiApiError;
      return (
        error instanceof AventiApiError &&
        apiError.status === 401 &&
        apiError.statusText === 'Unauthorized' &&
        apiError.message === 'Authentication required'
      );
    },
  );
  assert.equal(fetchCalled, false);
});

test('allows public requests without auth', async () => {
  let authorization: string | null = 'unexpected';
  mockFetch((_input, init) => {
    authorization = new Headers(init?.headers).get('authorization');
    return jsonResponse({ status: 'ok', service: 'aventi-backend' });
  });

  const api = new AventiApiClient({
    baseUrl: 'https://api.example.test',
    getAccessToken: () => null,
  });

  await api.getHealth();

  assert.equal(authorization, null);
});

test('keeps public location resolution JSON encoded without auth', async () => {
  let authorization: string | null = 'unexpected';
  let contentType: string | null = null;
  let body: unknown = null;
  mockFetch(async (_input, init) => {
    const headers = new Headers(init?.headers);
    authorization = headers.get('authorization');
    contentType = headers.get('content-type');
    body = JSON.parse(String(init?.body));
    return jsonResponse({ latitude: 39.7392, longitude: -104.9903 });
  });

  const api = new AventiApiClient({
    baseUrl: 'https://api.example.test',
    getAccessToken: () => null,
  });

  await api.resolveLocation({ latitude: 39.7392, longitude: -104.9903 });

  assert.equal(authorization, null);
  assert.equal(contentType, 'application/json');
  assert.deepEqual(body, { latitude: 39.7392, longitude: -104.9903 });
});

test('keeps public requests available when token lookup fails', async () => {
  let fetchCalled = false;
  mockFetch(() => {
    fetchCalled = true;
    return jsonResponse({ status: 'ok', service: 'aventi-backend' });
  });

  const api = new AventiApiClient({
    baseUrl: 'https://api.example.test',
    getAccessToken: () => {
      throw new Error('refresh failed');
    },
  });

  await api.getHealth();

  assert.equal(fetchCalled, true);
});

test('sends feed market context in the query string', async () => {
  let requestedUrl: string | null = null;
  let authorization: string | null = null;
  mockFetch((input, init) => {
    requestedUrl = String(input);
    authorization = new Headers(init?.headers).get('authorization');
    return jsonResponse({
      items: [],
      inventoryStatus: 'no_matches',
      warmupTriggered: false,
    });
  });

  const api = new AventiApiClient({
    baseUrl: 'https://api.example.test',
    getAccessToken: () => 'feed-token',
  });

  await api.getFeed({
    latitude: 39.7392,
    longitude: -104.9903,
    marketCity: 'Denver',
    marketState: 'CO',
    marketCountry: 'US',
    limit: 20,
    filters: {
      date: 'week',
      price: 'any',
      radiusMiles: 25,
      vibes: ['solo-friendly'],
      categories: ['comedy'],
    },
  });

  assert.equal(authorization, 'Bearer feed-token');
  const expectedQuery =
    'limit=20&date=week&latitude=39.7392&longitude=-104.9903' +
    '&marketCity=Denver&marketState=CO&marketCountry=US' +
    '&price=any&radiusMiles=25&vibes=solo-friendly&categories=comedy';
  assert.equal(
    requestedUrl,
    `https://api.example.test/v1/feed?${expectedQuery}`,
  );
});
