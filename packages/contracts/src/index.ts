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

export interface HealthResponse {
  status: 'ok';
  service: string;
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

export interface LocationResolvePayload {
  latitude: number;
  longitude: number;
}

export interface LocationResolveResponse extends ProfileLocationPayload {
  formattedAddress?: string | null;
}

export interface BootstrapMeResponse {
  id: string;
  email?: string | null;
  created: boolean;
  profile: MeProfile;
}

export interface GetMeResponse {
  id: string;
  email?: string | null;
  preferences: UserPreferences;
  profile?: MeProfile;
}

export interface UpdateMyLocationResponse {
  ok: true;
  userId: string;
  profile: MeProfile;
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

export interface SwipeResponse {
  accepted: true;
  remainingFreeSwipes?: number;
  remainingFreePreferenceActions?: number;
}

export interface FeedImpressionResponse {
  ok: true;
}

export interface UpdatePreferencesResponse {
  ok: true;
}

export interface ResetSeenEventsResponse {
  ok: true;
  deleted: number;
}

export interface MarketSeenPayload {
  city: string;
  state?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface MarketSeenResponse {
  ok: true;
  marketKey: string;
  bootstrapped: boolean;
}

export interface SaveFavoriteResponse {
  ok: true;
  eventId: string;
}

export interface DeleteFavoriteResponse {
  ok: true;
  eventId: string;
}

export interface EventReportPayload {
  reason: ReportReason;
  details?: string;
}

export interface EventReportResponse {
  ok: true;
  eventId: string;
  reportCount: number;
  hidden: boolean;
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

export interface AdminEnqueueMarketScanPayload {
  marketKey: string;
}

export interface AdminWorkerJobSummary {
  queued: number;
  sent: number;
  processing: number;
  succeeded24h: number;
  failed24h: number;
  dead: number;
  oldestQueuedAt?: string | null;
  lastSuccessAt?: string | null;
  lastFailureAt?: string | null;
}

export interface AdminWorkerJobTypeSummary {
  jobType: string;
  queued: number;
  sent: number;
  processing: number;
  succeeded24h: number;
  failed24h: number;
  dead: number;
}

export interface AdminWorkerJobRecent {
  id: string;
  jobType: string;
  status: string;
  marketKey?: string | null;
  schedulerRunId?: string | null;
  ingestRunId?: string | null;
  payloadSummary?: Record<string, unknown>;
  result?: Record<string, unknown>;
  attempts: number;
  maxAttempts: number;
  queuedAt: string;
  sentAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  lastError?: string | null;
  runId?: string | null;
}

export interface AdminWorkerJobsDashboard {
  summary: AdminWorkerJobSummary;
  byType: AdminWorkerJobTypeSummary[];
  recent: AdminWorkerJobRecent[];
}

export type AdminHealthStatus = 'Healthy' | 'Needs attention' | 'No data yet' | 'Setup needed';

export interface AdminAppHealthDashboard {
  summary: {
    status: AdminHealthStatus;
    eventsAvailableThisWeek: number;
    upcomingEvents: number;
    activeMarkets: number;
    activeUsers7d: number;
    feedViews7d: number;
    saves7d: number;
  };
  events: {
    status: AdminHealthStatus;
    hidden: number;
    missingImages: number;
    needsAttention: number;
    reported30d: number;
  };
  discovery: {
    status: AdminHealthStatus;
    eventsFound7d: number;
    eventsInserted7d: number;
    lastSuccessfulImportAt?: string | null;
    lastFailedImportAt?: string | null;
  };
  people: {
    status: AdminHealthStatus;
    activeUsers7d: number;
    feedViews7d: number;
    saves7d: number;
  };
  attention: {
    status: AdminHealthStatus;
    emptyMarkets: number;
    eventsNeedingAttention: number;
    missingImages: number;
    reportedEvents30d: number;
  };
}

export interface AdminSchedulerRunJob {
  id: string;
  jobType: string;
  status: string;
  marketKey?: string | null;
  attempts: number;
  maxAttempts: number;
  queuedAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  lastError?: string | null;
  payloadSummary?: Record<string, unknown>;
  result?: Record<string, unknown>;
  ingestRunId?: string | null;
  ingestStatus?: string | null;
  discoveredCount?: number | null;
  insertedCount?: number | null;
  traceSteps: Array<{
    label: string;
    status: 'pending' | 'current' | 'complete' | 'failed' | string;
  }>;
}

export interface AdminSchedulerRunSummary {
  id: string;
  triggerType: 'cron' | 'admin' | 'smoke' | string;
  status: 'running' | 'succeeded' | 'failed' | string;
  startedAt?: string | null;
  finishedAt?: string | null;
  marketsConsidered: number;
  marketsEnqueued: number;
  jobsEnqueued: number;
  limit?: number | null;
  error?: string | null;
  result: Record<string, unknown>;
  jobs: AdminSchedulerRunJob[];
}

export interface AdminQueueStatus {
  configured: boolean;
  reachable?: boolean;
  reason?: string;
  error?: string;
  approximateDepth?: number;
  approximateNotVisible?: number;
  oldestMessageAgeSeconds?: number;
}

export interface AdminSystemResponse {
  workerJobs: AdminWorkerJobsDashboard;
  schedulerRuns: AdminSchedulerRunSummary[];
  rawRecentErrors: Array<{
    source: string;
    id: string;
    occurredAt?: string | null;
    error?: string | null;
  }>;
  queues: {
    main: AdminQueueStatus;
    dlq: AdminQueueStatus;
  };
  eventBridge: {
    configured: boolean;
    enabled: boolean;
    scheduleExpression?: string | null;
    lastRun?: AdminSchedulerRunSummary | null;
  };
  providers: {
    googleApiKeyConfigured: boolean;
    serpApiKeyConfigured: boolean;
    pollinationsApiKeyConfigured: boolean;
  };
  retention: {
    succeededJobsDays: number;
    failedDeadJobsDays: number;
    schedulerRunsDays: number;
    automaticCleanupEnabled: boolean;
    candidates: {
      succeededJobs: number;
      failedDeadJobs: number;
      schedulerRuns: number;
    };
  };
}

export interface AdminFeedDiagnosticResponse {
  marketKey: string;
  city: string;
  state?: string | null;
  country: string;
  visibleEvents7d: number;
  upcomingOccurrences: number;
  hiddenEvents: number;
  pendingVerification: number;
  suspectOrInactive: number;
  missingImages: number;
  lastSuccessfulScan?: string | null;
  lastFailedScan?: string | null;
  lastScanCompletedAt?: string | null;
  lastScanSucceededAt?: string | null;
  lastError?: string | null;
  activeUsers: number;
  filtersProducingZeroResults: string[];
}

export interface AdminSmokeActionResponse {
  ok?: true;
  status?: string;
  schedulerRunId?: string;
  jobsEnqueued?: number;
  jobId?: string;
  eventId?: string;
  reason?: string;
  eventsAvailableThisWeek?: number;
  feedItemsReturned?: number;
  hasMore?: boolean;
  marketKey?: string;
  diagnostic?: AdminFeedDiagnosticResponse;
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
  workerJobs: AdminWorkerJobsDashboard;
  appHealth: AdminAppHealthDashboard;
}

export const RANKING_CONSTANTS = {
  BASELINE_WEIGHT: 1.0,
  LIKE_MULTIPLIER: 1.1,
  LIKE_BONUS: 0.1,
  PASS_MULTIPLIER: 0.95,
  FREE_PREFERENCE_ACTION_LIMIT_PER_DAY: 10,
  FREE_SWIPE_LIMIT_PER_DAY: 10,
} as const;
