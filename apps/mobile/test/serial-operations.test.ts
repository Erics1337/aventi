import assert from 'node:assert/strict';
import test from 'node:test';
import { createSerialOperations } from '../lib/serial-operations.ts';

test('account switching waits for purchase and reconciliation, including failure', async () => {
  const run = createSerialOperations();
  let finishPurchase!: () => void;
  const purchasePending = new Promise<void>(resolve => { finishPurchase = resolve; });
  const steps: string[] = [];
  const purchase = run(async () => {
    steps.push('identity A');
    await purchasePending;
    steps.push('reconcile A');
    throw new Error('account changed');
  });
  const switched = run(async () => { steps.push('identity B'); });
  await Promise.resolve();
  assert.deepEqual(steps, ['identity A']);
  finishPurchase();
  await assert.rejects(purchase, /account changed/);
  await switched;
  assert.deepEqual(steps, ['identity A', 'reconcile A', 'identity B']);
});
