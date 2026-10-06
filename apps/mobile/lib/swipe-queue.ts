import AsyncStorage from '@react-native-async-storage/async-storage';
import type { SwipePayload } from '@aventi/contracts';
import { AventiApiError } from '@aventi/api-client';

const STORAGE_PREFIX = 'aventi.pending-swipes.v2';
const MAX_RETRY_DELAY_MS = 5 * 60_000;

export interface PendingSwipeAction {
  accountId: string;
  payload: SwipePayload;
  attempts: number;
  createdAt: string;
  retryAt: string;
}

interface QueueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface FlushResult {
  sent: SwipePayload[];
  pending: PendingSwipeAction[];
  rejected: Array<{ payload: SwipePayload; error: unknown }>;
}

function storageKey(accountId: string): string {
  return `${STORAGE_PREFIX}:${accountId}`;
}

function isPermanentFailure(error: unknown): boolean {
  return error instanceof AventiApiError && error.status >= 400 && error.status < 500 && error.status !== 401 && error.status !== 408 && error.status !== 429;
}

function retryDelay(attempts: number): number {
  return Math.min(MAX_RETRY_DELAY_MS, 1_000 * 2 ** Math.min(attempts, 8));
}

export class PendingSwipeQueue {
  private flushes = new Map<string, Promise<FlushResult>>();
  private storageOperations = new Map<string, Promise<void>>();
  private generations = new Map<string, number>();

  constructor(private readonly storage: QueueStorage = AsyncStorage) {}

  private generation(accountId: string): number {
    return this.generations.get(accountId) ?? 0;
  }

  private async withStorageLock<T>(accountId: string, operation: () => Promise<T>): Promise<T> {
    const previous = this.storageOperations.get(accountId) ?? Promise.resolve();
    let release!: () => void;
    const current = new Promise<void>((resolve) => { release = resolve; });
    const chained = previous.then(() => current);
    this.storageOperations.set(accountId, chained);
    await previous;
    try {
      return await operation();
    } finally {
      release();
      if (this.storageOperations.get(accountId) === chained) this.storageOperations.delete(accountId);
    }
  }

  private async read(accountId: string): Promise<PendingSwipeAction[]> {
    const raw = await this.storage.getItem(storageKey(accountId));
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw) as PendingSwipeAction[];
      return Array.isArray(parsed)
        ? parsed.filter((item) => item.accountId === accountId && Boolean(item.payload?.actionId))
        : [];
    } catch {
      await this.storage.removeItem(storageKey(accountId));
      return [];
    }
  }

  list(accountId: string): Promise<PendingSwipeAction[]> {
    return this.withStorageLock(accountId, () => this.read(accountId));
  }

  async enqueue(accountId: string, payload: SwipePayload): Promise<PendingSwipeAction> {
    return this.withStorageLock(accountId, async () => {
      const current = await this.read(accountId);
      const existing = current.find((item) => item.payload.actionId === payload.actionId);
      if (existing) return existing;
      const now = new Date().toISOString();
      const item: PendingSwipeAction = { accountId, payload, attempts: 0, createdAt: now, retryAt: now };
      await this.storage.setItem(storageKey(accountId), JSON.stringify([...current, item]));
      return item;
    });
  }

  async clearAccount(accountId: string): Promise<void> {
    this.cancelAccount(accountId);
    await this.withStorageLock(accountId, () => this.storage.removeItem(storageKey(accountId)));
  }

  cancelAccount(accountId: string): void {
    this.generations.set(accountId, this.generation(accountId) + 1);
  }

  flush(
    accountId: string,
    send: (payload: SwipePayload) => Promise<unknown>,
    options?: { force?: boolean },
  ): Promise<FlushResult> {
    const inFlight = this.flushes.get(accountId);
    if (inFlight) return inFlight;
    const promise = this.flushNow(accountId, send, options).finally(() => {
      this.flushes.delete(accountId);
    });
    this.flushes.set(accountId, promise);
    return promise;
  }

  private async flushNow(
    accountId: string,
    send: (payload: SwipePayload) => Promise<unknown>,
    options?: { force?: boolean },
  ): Promise<FlushResult> {
    const generation = this.generation(accountId);
    const sent: SwipePayload[] = [];
    const rejected: Array<{ payload: SwipePayload; error: unknown }> = [];

    while (this.generation(accountId) === generation) {
      const queue = await this.list(accountId);
      const item = queue[0];
      if (!item) break;
      if (!options?.force && Date.parse(item.retryAt) > Date.now()) {
        break;
      }
      try {
        if (this.generation(accountId) !== generation) break;
        await send(item.payload);
        sent.push(item.payload);
        await this.withStorageLock(accountId, async () => {
          if (this.generation(accountId) !== generation) return;
          const latest = await this.read(accountId);
          const next = latest.filter((candidate) => candidate.payload.actionId !== item.payload.actionId);
          if (next.length > 0) await this.storage.setItem(storageKey(accountId), JSON.stringify(next));
          else await this.storage.removeItem(storageKey(accountId));
        });
      } catch (error) {
        if (isPermanentFailure(error)) {
          rejected.push({ payload: item.payload, error });
          await this.withStorageLock(accountId, async () => {
            if (this.generation(accountId) !== generation) return;
            const latest = await this.read(accountId);
            const next = latest.filter((candidate) => candidate.payload.actionId !== item.payload.actionId);
            if (next.length > 0) await this.storage.setItem(storageKey(accountId), JSON.stringify(next));
            else await this.storage.removeItem(storageKey(accountId));
          });
          continue;
        }
        const attempts = item.attempts + 1;
        await this.withStorageLock(accountId, async () => {
          if (this.generation(accountId) !== generation) return;
          const latest = await this.read(accountId);
          const next = latest.map((candidate) => candidate.payload.actionId === item.payload.actionId
            ? { ...candidate, attempts, retryAt: new Date(Date.now() + retryDelay(attempts)).toISOString() }
            : candidate);
          await this.storage.setItem(storageKey(accountId), JSON.stringify(next));
        });
        break;
      }
    }
    const pending = await this.list(accountId);
    return { sent, pending, rejected };
  }
}

export const pendingSwipeQueue = new PendingSwipeQueue();
