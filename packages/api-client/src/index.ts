import type {
  AdminDashboardResponse,
  AdminEnqueueMarketScanResponse,
  AdminImportMarketsCatalogResponse,
  AdminUserLocationsResponse,
  AccountDeletionStatus,
  DestinationsResponse,
  EventInsights,
  FeedImpressionPayload,
  FeedRequest,
  FeedResponse,
  FavoritesResponse,
  MeProfile,
  MembershipEntitlements,
  MembershipReconcilePayload,
  MembershipReconcileResponse,
  ProfileLocationPayload,
  ReportReason,
  SwipePayload,
  SwipeResponse,
  UserPreferences,
} from '@aventi/contracts';

export interface AventiApiClientOptions {
  baseUrl: string;
  getAccessToken?: () => Promise<string | null> | string | null;
}

export class AventiApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body?: unknown,
  ) {
    super(`Aventi API error ${status}`);
    this.name = 'AventiApiError';
  }
}

export class AventiApiClient {
  constructor(private readonly options: AventiApiClientOptions) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const token = await this.options.getAccessToken?.();
    const response = await fetch(`${this.options.baseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });

    if (!response.ok) {
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        body = undefined;
      }
      throw new AventiApiError(response.status, body);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  getHealth() {
    return this.request<{ status: 'ok'; service: string }>(`/v1/health`);
  }

  bootstrapMe() {
    return this.request<{
      id: string;
      email?: string | null;
      created: boolean;
      profile: MeProfile;
    }>(`/v1/me/bootstrap`, { method: 'POST' });
  }

  getMe() {
    return this.request<{
      id: string;
      email?: string | null;
      preferences: UserPreferences;
      profile?: MeProfile;
    }>(`/v1/me`);
  }

  updateMyLocation(payload: ProfileLocationPayload) {
    return this.request<{ ok: true; userId: string; profile: MeProfile }>(`/v1/me/location`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  getFeed(payload: FeedRequest) {
    const search = new URLSearchParams({
      limit: String(payload.limit ?? 20),
      date: payload.filters.date,
      latitude: String(payload.latitude),
      longitude: String(payload.longitude),
      ...(payload.marketCity ? { marketCity: payload.marketCity } : {}),
      ...(payload.marketState ? { marketState: payload.marketState } : {}),
      ...(payload.marketCountry ? { marketCountry: payload.marketCountry } : {}),
      ...(payload.destinationId ? { destinationId: payload.destinationId } : {}),
      ...(payload.filters.startDate ? { startDate: payload.filters.startDate } : {}),
      ...(payload.filters.endDate ? { endDate: payload.filters.endDate } : {}),
      ...(payload.filters.query ? { query: payload.filters.query } : {}),
      ...(payload.filters.timeOfDay ? { timeOfDay: payload.filters.timeOfDay } : {}),
      ...(payload.filters.price ? { price: payload.filters.price } : {}),
      ...(payload.filters.radiusMiles ? { radiusMiles: String(payload.filters.radiusMiles) } : {}),
      ...(payload.filters.premiumAgeRestriction
        ? { premiumAgeRestriction: payload.filters.premiumAgeRestriction }
        : {}),
      ...(payload.cursor ? { cursor: payload.cursor } : {}),
    });
    for (const vibe of payload.filters.vibes ?? []) {
      search.append('vibes', vibe);
    }
    for (const category of payload.filters.categories ?? []) {
      search.append('categories', category);
    }
    return this.request<FeedResponse>(`/v1/feed?${search.toString()}`);
  }

  refreshFeed(payload: FeedRequest) {
    return this.request<FeedResponse>(`/v1/feed/refresh`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  postSwipe(payload: SwipePayload, accessToken?: string) {
    return this.request<SwipeResponse>(`/v1/swipes`, {
      method: 'POST',
      ...(accessToken ? { headers: { Authorization: `Bearer ${accessToken}` } } : {}),
      body: JSON.stringify(payload),
    });
  }

  recordFeedImpression(payload: FeedImpressionPayload) {
    return this.request<{ ok: true }>(`/v1/feed/impressions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  updatePreferences(payload: UserPreferences) {
    return this.request<{ ok: true }>(`/v1/me/preferences`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  resetSeenEvents() {
    return this.request<{ ok: true; deleted: number }>(`/v1/me/seen-events/reset`, {
      method: 'POST',
    });
  }

  markMarketSeen(payload: {
    city: string;
    state?: string | null;
    country?: string | null;
    latitude?: number | null;
    longitude?: number | null;
  }) {
    return this.request<{ ok: true; marketKey: string; bootstrapped: boolean }>(
      `/v1/me/market-seen`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    );
  }

  getEntitlements() {
    return this.request<MembershipEntitlements>(`/v1/membership/entitlements`);
  }

  getMembershipProducts() {
    return this.request<{ purchasesEnabled: boolean; products: Array<{ period: 'monthly' | 'annual'; productId: string }> }>('/v1/membership/products');
  }

  reconcileMembership(payload: MembershipReconcilePayload) {
    return this.request<MembershipReconcileResponse>(`/v1/membership/reconcile`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  searchDestinations(query: string) {
    const search = new URLSearchParams({ q: query });
    return this.request<DestinationsResponse>(`/v1/destinations?${search.toString()}`);
  }

  getEventInsights(eventId: string, context?: Pick<FeedRequest['filters'], 'radiusMiles' | 'startDate' | 'endDate' | 'premiumAgeRestriction' | 'categories' | 'vibes'> & { destinationId?: string }) {
    const search = new URLSearchParams({
      ...(context?.radiusMiles ? { radiusMiles: String(context.radiusMiles) } : {}),
      ...(context?.destinationId ? { destinationId: context.destinationId } : {}),
      ...(context?.startDate ? { startDate: context.startDate } : {}),
      ...(context?.endDate ? { endDate: context.endDate } : {}),
      ...(context?.premiumAgeRestriction ? { ageRestriction: context.premiumAgeRestriction } : {}),
    });
    for (const category of context?.categories ?? []) search.append('categories', category);
    for (const vibe of context?.vibes ?? []) search.append('vibes', vibe);
    const suffix = search.size > 0 ? `?${search.toString()}` : '';
    return this.request<EventInsights>(`/v1/events/${encodeURIComponent(eventId)}/insights${suffix}`);
  }

  requestAccountDeletion() {
    return this.request<AccountDeletionStatus>(`/v1/me`, { method: 'DELETE' });
  }

  getAccountDeletionStatus() {
    return this.request<AccountDeletionStatus>(`/v1/me/deletion`);
  }

  getAdminDashboard() {
    return this.request<AdminDashboardResponse>(`/v1/admin/dashboard`);
  }

  getAdminUserLocations() {
    return this.request<AdminUserLocationsResponse>(`/v1/admin/user-locations`);
  }

  postAdminImportMarketsFromCatalog() {
    return this.request<AdminImportMarketsCatalogResponse>(`/v1/admin/import-markets-from-catalog`, {
      method: 'POST',
    });
  }

  postAdminEnqueueMarketScan(payload: { marketKey: string }) {
    return this.request<AdminEnqueueMarketScanResponse>(`/v1/admin/markets/enqueue-scan`, {
      method: 'POST',
      body: JSON.stringify({ marketKey: payload.marketKey }),
    });
  }

  getFavorites() {
    return this.request<FavoritesResponse>(`/v1/favorites`);
  }

  saveFavorite(eventId: string) {
    return this.request<{ ok: true; eventId: string }>(`/v1/favorites/${eventId}`, {
      method: 'PUT',
    });
  }

  deleteFavorite(eventId: string) {
    return this.request<{ ok: true; eventId: string }>(`/v1/favorites/${eventId}`, {
      method: 'DELETE',
    });
  }

  reportEvent(eventId: string, payload: { reason: ReportReason; details?: string }) {
    return this.request<{ ok: true; eventId: string; reportCount: number; hidden: boolean }>(
      `/v1/events/${eventId}/report`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    );
  }
}
