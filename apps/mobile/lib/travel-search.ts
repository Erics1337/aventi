const DAY_MS = 86_400_000;

export interface TravelDateRange {
  startDate: string;
  endDate: string;
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function defaultTravelDateRange(now = new Date()): TravelDateRange {
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const end = new Date(start.getTime() + 6 * DAY_MS);
  return { startDate: isoDate(start), endDate: isoDate(end) };
}

export function validateTravelDateRange(range: TravelDateRange, now = new Date()): string | null {
  const start = Date.parse(`${range.startDate}T00:00:00Z`);
  const end = Date.parse(`${range.endDate}T00:00:00Z`);
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 'Enter dates as YYYY-MM-DD.';
  if (start < today) return 'Travel dates cannot be in the past.';
  if (start > today + 60 * DAY_MS) return 'Travel dates can start up to 60 days from today.';
  if (end < start) return 'End date must be on or after the start date.';
  if (end - start > 6 * DAY_MS) return 'Choose a range of 7 days or fewer.';
  return null;
}
