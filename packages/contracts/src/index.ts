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
  | 'late-night';

export type ReportReason = 'invalid' | 'cancelled' | 'duplicate' | 'unsafe' | 'other';

export type EventCategory = 'nightlife' | 'dining' | 'concerts' | 'wellness' | 'experiences';

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
}

export type FeedInventoryStatus = 'ready' | 'warming' | 'targeted_warming' | 'no_matches';

export interface FeedResponse {
  items: EventCard[];
  nextCursor?: string | null;
  fallbackStatus?: 'none' | 'relaxed_filters' | 'insufficient_inventory' | 'no_filter_matches';
  remainingFreeSwipes?: number;
  remainingFreePreferenceActions?: number;
  marketKey?: string | null;
  inventoryStatus: FeedInventoryStatus;
  warmupTriggered: boolean;
}

export interface FavoritesResponse {
  items: string[];
  events?: EventCard[];
}

export interface SwipePayload {
  eventId: string;
  action: SwipeAction;
  surfacedAt: string;
  position: number;
  vibes: EventVibeTag[];
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
  isPremium: boolean;
  plan: 'free' | 'unlimited';
  unlimitedSwipes: boolean;
  advancedFilters: boolean;
  travelMode: boolean;
  insiderTips: boolean;
  validUntil?: string | null;
}

export type AdminMarketHeatTier = 'hot' | 'warm' | 'cold';

export interface AdminMarketSummary {
  marketKey: string;
  city: string;
  state?: string | null;
  country: string;
  heatTier: AdminMarketHeatTier;
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
