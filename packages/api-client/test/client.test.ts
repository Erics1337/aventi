import assert from 'node:assert/strict';
import test from 'node:test';
import { AventiApiClient, AventiApiError } from '../src/index';

test('getFeed serializes launch filters and destination', async () => {
  let requestedUrl = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify({ items: [], inventoryStatus: 'ready', warmupTriggered: false }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
  try {
    const client = new AventiApiClient({ baseUrl: 'https://api.aventi.test' });
    await client.getFeed({
      latitude: 40.7,
      longitude: -74,
      destinationId: 'us:ny:new-york',
      filters: {
        date: 'week',
        startDate: '2026-10-01',
        endDate: '2026-10-07',
        radiusMiles: 10,
        premiumAgeRestriction: '21+',
      },
    });
    const url = new URL(requestedUrl);
    assert.equal(url.pathname, '/v1/feed');
    assert.equal(url.searchParams.get('destinationId'), 'us:ny:new-york');
    assert.equal(url.searchParams.get('startDate'), '2026-10-01');
    assert.equal(url.searchParams.get('endDate'), '2026-10-07');
    assert.equal(url.searchParams.get('radiusMiles'), '10');
    assert.equal(url.searchParams.get('premiumAgeRestriction'), '21+');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('postSwipe preserves stable actionId and like semantics in one request', async () => {
  let requestBody = '';
  let authorization = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_input, init) => {
    requestBody = String(init?.body);
    authorization = new Headers(init?.headers).get('authorization') ?? '';
    return new Response(JSON.stringify({ accepted: true, actionId: 'action-1', favorite: true }), { status: 200 });
  };
  try {
    const client = new AventiApiClient({ baseUrl: 'https://api.aventi.test' });
    await client.postSwipe({ actionId: 'action-1', eventId: 'event-1', action: 'like', surfacedAt: '2026-09-26T00:00:00Z', position: 0, vibes: [] }, 'account-a-token');
    assert.deepEqual(JSON.parse(requestBody), { actionId: 'action-1', eventId: 'event-1', action: 'like', surfacedAt: '2026-09-26T00:00:00Z', position: 0, vibes: [] });
    assert.equal(authorization, 'Bearer account-a-token');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('event insights include the active discovery context', async () => {
  let requestedUrl = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify({ status: 'pending', retryAfterSeconds: 3 }), { status: 200 });
  };
  try {
    const client = new AventiApiClient({ baseUrl: 'https://api.aventi.test' });
    await client.getEventInsights('event/id', {
      radiusMiles: 10,
      startDate: '2026-10-01',
      endDate: '2026-10-07',
      premiumAgeRestriction: '21+',
      categories: ['concerts'],
      vibes: ['live-music'],
    });
    const url = new URL(requestedUrl);
    assert.equal(url.pathname, '/v1/events/event%2Fid/insights');
    assert.equal(url.searchParams.get('radiusMiles'), '10');
    assert.equal(url.searchParams.get('ageRestriction'), '21+');
    assert.deepEqual(url.searchParams.getAll('categories'), ['concerts']);
    assert.deepEqual(url.searchParams.getAll('vibes'), ['live-music']);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('API failures retain status and structured body', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'limit reached' }), { status: 429 });
  try {
    const client = new AventiApiClient({ baseUrl: 'https://api.aventi.test' });
    await assert.rejects(client.getEntitlements(), (error) => {
      assert.ok(error instanceof AventiApiError);
      assert.equal(error.status, 429);
      assert.deepEqual(error.body, { detail: 'limit reached' });
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
