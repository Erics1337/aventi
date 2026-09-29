import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultTravelDateRange, validateTravelDateRange } from '../lib/travel-search';

const NOW = new Date('2026-09-26T16:00:00Z');

test('travel date defaults cover exactly seven calendar days', () => {
  assert.deepEqual(defaultTravelDateRange(NOW), { startDate: '2026-09-26', endDate: '2026-10-02' });
});

test('travel range rejects past, over-seven-day, and over-sixty-day searches', () => {
  assert.match(validateTravelDateRange({ startDate: '2026-09-25', endDate: '2026-09-26' }, NOW) ?? '', /past/);
  assert.match(validateTravelDateRange({ startDate: '2026-09-26', endDate: '2026-10-03' }, NOW) ?? '', /7 days/);
  assert.match(validateTravelDateRange({ startDate: '2026-11-26', endDate: '2026-11-26' }, NOW) ?? '', /60 days/);
});

test('travel range accepts a future seven-day search', () => {
  assert.equal(validateTravelDateRange({ startDate: '2026-10-10', endDate: '2026-10-16' }, NOW), null);
});
