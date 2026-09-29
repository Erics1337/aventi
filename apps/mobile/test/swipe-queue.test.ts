import assert from 'node:assert/strict';
import test from 'node:test';
import { AventiApiError } from '@aventi/api-client';
import type { SwipePayload } from '@aventi/contracts';
import { PendingSwipeQueue } from '../lib/swipe-queue';
import { uuidV4FromBytes } from '../lib/uuid';

class MemoryStorage {
  values = new Map<string, string>();
  async getItem(key: string) { return this.values.get(key) ?? null; }
  async setItem(key: string, value: string) { this.values.set(key, value); }
  async removeItem(key: string) { this.values.delete(key); }
}

function payload(actionId: string): SwipePayload {
  return { actionId, eventId: 'event-1', action: 'like', surfacedAt: '2026-09-26T00:00:00Z', position: 0, vibes: [] };
}

test('queue persists by account and deduplicates actionId', async () => {
  const storage = new MemoryStorage();
  const first = new PendingSwipeQueue(storage);
  await first.enqueue('user-a', payload('action-1'));
  await first.enqueue('user-a', payload('action-1'));
  const restored = await new PendingSwipeQueue(storage).list('user-a');
  assert.equal(restored.length, 1);
  assert.equal(restored[0].payload.actionId, 'action-1');
  assert.deepEqual(await first.list('user-b'), []);
});

test('action ids are database-safe UUIDs', () => {
  assert.match(uuidV4FromBytes(Uint8Array.from({ length: 16 }, (_, index) => index)), /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
});

test('transient errors retain an action for retry and later success removes it', async () => {
  const storage = new MemoryStorage();
  const queue = new PendingSwipeQueue(storage);
  await queue.enqueue('user-a', payload('action-1'));
  const failed = await queue.flush('user-a', async () => { throw new Error('offline'); }, { force: true });
  assert.equal(failed.pending.length, 1);
  assert.equal(failed.pending[0].attempts, 1);
  const succeeded = await queue.flush('user-a', async () => ({ accepted: true }), { force: true });
  assert.equal(succeeded.sent.length, 1);
  assert.deepEqual(await queue.list('user-a'), []);
});

test('permanent API rejection is removed and reported for optimistic rollback', async () => {
  const queue = new PendingSwipeQueue(new MemoryStorage());
  await queue.enqueue('user-a', payload('action-1'));
  const result = await queue.flush('user-a', async () => { throw new AventiApiError(422, { detail: 'invalid event' }); }, { force: true });
  assert.equal(result.rejected.length, 1);
  assert.equal(result.rejected[0].payload.actionId, 'action-1');
  assert.deepEqual(result.pending, []);
});

test('409 event rejection is permanent instead of retrying forever', async () => {
  const queue = new PendingSwipeQueue(new MemoryStorage());
  await queue.enqueue('user-a', payload('action-1'));
  const result = await queue.flush('user-a', async () => { throw new AventiApiError(409); }, { force: true });
  assert.equal(result.rejected.length, 1);
  assert.equal(result.pending.length, 0);
});

test('enqueue during an in-flight flush is preserved and processed', async () => {
  const queue = new PendingSwipeQueue(new MemoryStorage());
  await queue.enqueue('user-a', payload('action-1'));
  let release!: () => void;
  let entered!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const sending = new Promise<void>((resolve) => { entered = resolve; });
  const sent: string[] = [];
  const flush = queue.flush('user-a', async (item) => {
    sent.push(item.actionId);
    if (item.actionId === 'action-1') {
      entered();
      await gate;
    }
  }, { force: true });
  await sending;
  await queue.enqueue('user-a', payload('action-2'));
  release();
  await flush;
  assert.deepEqual(sent, ['action-1', 'action-2']);
  assert.deepEqual(await queue.list('user-a'), []);
});

test('clearAccount invalidates in-flight writeback', async () => {
  const storage = new MemoryStorage();
  const queue = new PendingSwipeQueue(storage);
  await queue.enqueue('user-a', payload('action-1'));
  let release!: () => void;
  let entered!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const sending = new Promise<void>((resolve) => { entered = resolve; });
  const flush = queue.flush('user-a', async () => { entered(); await gate; }, { force: true });
  await sending;
  await queue.clearAccount('user-a');
  release();
  await flush;
  assert.deepEqual(await queue.list('user-a'), []);
});

test('cancelAccount keeps an in-flight action for its original account', async () => {
  const queue = new PendingSwipeQueue(new MemoryStorage());
  await queue.enqueue('user-a', payload('action-1'));
  let release!: () => void;
  let entered!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const sending = new Promise<void>((resolve) => { entered = resolve; });
  const flush = queue.flush('user-a', async () => { entered(); await gate; }, { force: true });
  await sending;
  queue.cancelAccount('user-a');
  release();
  await flush;
  assert.equal((await queue.list('user-a')).length, 1);
});
