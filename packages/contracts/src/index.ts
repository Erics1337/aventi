export type SwipeAction = 'like' | 'pass';

export type EventVibeTag =
  | 'chill'
  | 'energetic'
  | 'intellectual'
  | 'romantic'
  | 'social'
  | 'luxury'
  | 'live-music'
  | 'wellness'
  | 'late-night'
  | 'solo-friendly'
  | 'family'
  | 'adventurous'
  | 'intimate'
  | 'underground';

export type ReportReason = 'invalid' | 'cancelled' | 'duplicate' | 'unsafe' | 'other';

export type EventCategory =
  | 'nightlife'
  | 'dining'
  | 'concerts'
  | 'wellness'
  | 'experiences'
  | 'comedy'
  | 'sports'
  | 'outdoors'
  | 'markets'
  | 'tech';

export interface TicketOffer {
  url: string;
  provider?: string | null;
  priceLabel?: string | null;
  isFree?: boolean | null;
}

export interface EventCard {
  id: string;
  title: string;
  description: string;
  category: EventCategory;
  venueName: string;
  city: string;
  startsAt: string;
  endsAt?: string | null;
  bookingUrl: string;
  imageUrl?: string | null;
  priceLabel?: string | null;
  isFree: boolean;
  radiusMiles?: number | null;
  vibes: EventVibeTag[];
  tags: string[];
  // SerpAPI enrichment fields
  venueRating?: number | null;
  venueReviewCount?: number | null;
  ticketOffers?: TicketOffer[];
}

export interface FeedFilters {
  date: 'today' | 'tomorrow' | 'weekend' | 'week';
  query?: string;
  /** Inclusive ISO calendar date. When present it takes precedence over `date`. */
  startDate?: string;
  /** Inclusive ISO calendar date, at most 60 days after startDate. */
  endDate?: string;
  timeOfDay?: 'morning' | 'afternoon' | 'evening' | 'night';
  price?: 'free' | 'paid' | 'any';
  radiusMiles?: number;
  vibes?: EventVibeTag[];
  categories?: EventCategory[];
  premiumAgeRestriction?: 'all' | '18+' | '21+';
}

export interface FeedRequest {
  cursor?: string;
  limit?: number;
  filters: FeedFilters;
  latitude: number;
  longitude: number;
  marketCity?: string;
  marketState?: string | null;
  marketCountry?: string | null;
  /** Canonical destination id returned by /v1/destinations. */
  destinationId?: string;
}

export type FeedInventoryStatus =
  | 'ready'
  | 'warming'
  | 'targeted_warming'
  | 'no_matches'
  | 'budget_paused'
  | 'unavailable'
  | 'unsupported';

export interface FeedResponse {
  items: EventCard[];
  nextCursor?: string | null;
  fallbackStatus?: 'none' | 'relaxed_filters' | 'insufficient_inventory' | 'no_filter_matches';
  remainingFreeSwipes?: number;
  remainingFreePreferenceActions?: number;
  marketKey?: string | null;
  inventoryStatus: FeedInventoryStatus;
  warmupTriggered: boolean;
  resetAt?: string | null;
  retryAt?: string | null;
}

export interface FavoritesResponse {
  items: string[];
  events?: EventCard[];
}

export interface SwipePayload {
  /** Client-generated stable id used to make retries idempotent. */
  actionId: string;
  eventId: string;
  action: SwipeAction;
  surfacedAt: string;
  position: number;
  vibes: EventVibeTag[];
}

export interface SwipeResponse {
  accepted: true;
  actionId: string;
  favorite: boolean;
  remainingFreeSwipes?: number;
  remainingFreePreferenceActions?: number;
  resetAt?: string | null;
}

export interface Destination {
  id: string;
  label: string;
  city: string;
  state: string;
  country: 'US';
  latitude: number;
  longitude: number;
  timezone?: string | null;
}

export interface DestinationsResponse {
  items: Destination[];
}

export interface EventInsights {
  status: 'ready' | 'pending' | 'unavailable';
  reason?: string;
  insight?: {
    summary: string;
    venueName?: string | null;
    city?: string | null;
    startsAt?: string | null;
    insiderTips: string[];
    sources: Array<{ label: string; url: string }>;
    compatibleEvents?: Array<{
      eventId: string;
      title: string;
      venueName?: string | null;
      startsAt?: string | null;
      bookingUrl?: string | null;
    }>;
    grounded: boolean;
  };
  generatedAt?: string | null;
  expiresAt?: string | null;
  jobId?: string | null;
  retryAfterSeconds?: number;
}

export interface MembershipReconcilePayload {
  appUserId: string;
  customerInfo: {
    originalAppUserId: string;
    activeEntitlementIds: string[];
    latestExpirationDate?: string | null;
    managementUrl?: string | null;
  };
}

export type MembershipReconcileResponse = MembershipEntitlements;

export type AccountDeletionState = 'not_requested' | 'pending' | 'processing' | 'completed' | 'failed';

export interface AccountDeletionStatus {
  status: AccountDeletionState;
  requestedAt?: string | null;
  completedAt?: string | null;
  retryAt?: string | null;
}

export interface FeedImpressionPayload {
  eventId: string;
  servedAt?: string;
  position?: number;
  affinityScore?: number;
  filters?: Record<string, unknown>;
}

export interface UserPreferences {
  categories: EventCategory[];
  vibes: EventVibeTag[];
  city?: string;
  radiusMiles: number;
}

export interface ProfileLocationPayload {
  latitude: number;
  longitude: number;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  timezone?: string | null;
}

export interface MeProfile {
  city?: string | null;
  state?: string | null;
  country?: string | null;
  timezone?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  onboarded: boolean;
}

export type VibeWeightMap = Partial<Record<EventVibeTag, number>>;

export interface MembershipEntitlements {
  purchasesEnabled?: boolean;
  isPremium: boolean;
  plan: 'free' | 'unlimited';
  unlimitedSwipes: boolean;
  advancedFilters: boolean;
  travelMode: boolean;
  insiderTips: boolean;
  validUntil?: string | null;
  productIdentifier?: string | null;
  status?: string | null;
  managementUrl?: string | null;
}

export type AdminMarketHeatTier = 'hot' | 'warm' | 'cold';

export interface AdminMarketSummary {
  marketKey: string;
  city: string;
  state?: string | null;
  country: string;
  heatTier: AdminMarketHeatTier;
  /** Approximate catalog / scan center when known (optional). */
  centerLatitude?: number | null;
  centerLongitude?: number | null;
  visibleEventCount7d: number;
  activeUserCount7d: number;
  activeUserCount14d: number;
  lastRequestedAt?: string | null;
  lastScanRequestedAt?: string | null;
  lastScanStartedAt?: string | null;
  lastScanCompletedAt?: string | null;
  lastScanSucceededAt?: string | null;
  scanLockUntil?: string | null;
  lastTargetedRequestedAt?: string | null;
  lastTargetedCompletedAt?: string | null;
  lastTargetedFilterSignature?: string | null;
  lastError?: string | null;
  updatedAt?: string | null;
}

export interface AdminIngestRunSummary {
  id: string;
  city?: string | null;
  status: string;
  sourceName?: string | null;
  sourceType?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  discoveredCount: number;
  insertedCount: number;
  errorMessage?: string | null;
  metadata: Record<string, unknown>;
}

export interface AdminVerificationSummary {
  status: string;
  active?: boolean | null;
  count: number;
  latestVerifiedAt?: string | null;
}

export interface AdminImportMarketsCatalogResponse {
  ok: true;
  synced: number;
  marketsConsidered: number;
  heat: {
    updated: number;
    hot: number;
    warm: number;
    cold: number;
  };
}

/** @deprecated use AdminImportMarketsCatalogResponse */
export type AdminSyncMarketsFromVenuesResponse = AdminImportMarketsCatalogResponse;

export interface AdminUserLocationPoint {
  userId: string;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  latitude: number;
  longitude: number;
  updatedAt?: string | null;
}

export interface AdminUserLocationsResponse {
  users: AdminUserLocationPoint[];
}

export interface AdminEnqueueMarketScanResponse {
  ok: true;
  jobId: string;
  marketKey: string;
}

export interface AdminDashboardResponse {
  rollup: {
    marketsTotal: number;
    hotMarkets: number;
    activeScans: number;
    visibleEvents7d: number;
    runningIngests: number;
    failedIngests: number;
    verificationBacklog: number;
  };
  markets: AdminMarketSummary[];
  ingestRuns: AdminIngestRunSummary[];
  verification: AdminVerificationSummary[];
  workerQueue: {
    configured: boolean;
    pollSeconds: number;
    endpointUrl?: string | null;
  };
}

export const RANKING_CONSTANTS = {
  BASELINE_WEIGHT: 1.0,
  LIKE_MULTIPLIER: 1.1,
  LIKE_BONUS: 0.1,
  PASS_MULTIPLIER: 0.95,
  FREE_PREFERENCE_ACTION_LIMIT_PER_DAY: 10,
  FREE_SWIPE_LIMIT_PER_DAY: 10,
} as const;
