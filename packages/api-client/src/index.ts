import type {
  AdminDashboardResponse,
  AdminEnqueueMarketScanPayload,
  AdminEnqueueMarketScanResponse,
  AdminFeedDiagnosticResponse,
  AdminImportMarketsCatalogResponse,
  AdminSmokeActionResponse,
  AdminSystemResponse,
  AdminUserLocationsResponse,
  BootstrapMeResponse,
  DeleteFavoriteResponse,
  EventReportPayload,
  EventReportResponse,
  FeedImpressionPayload,
  FeedImpressionResponse,
  FeedRequest,
  FeedResponse,
  FavoritesResponse,
  GetMeResponse,
  HealthResponse,
  LocationResolvePayload,
  LocationResolveResponse,
  MarketSeenPayload,
  MarketSeenResponse,
  MembershipEntitlements,
  ProfileLocationPayload,
  ResetSeenEventsResponse,
  SaveFavoriteResponse,
  SwipePayload,
  SwipeResponse,
  UpdateMyLocationResponse,
  UpdatePreferencesResponse,
  UserPreferences,
} from '@aventi/contracts';

export interface AventiApiClientOptions {
  baseUrl: string;
  getAccessToken?: () => Promise<string | null> | string | null;
}

type AuthMode = 'required' | 'optional';
type QueryPrimitive = string | number | boolean | null | undefined;
type QueryValue = QueryPrimitive | readonly QueryPrimitive[];

type JsonRequestInit = Omit<RequestInit, 'body'> & {
  auth?: AuthMode;
  body?: unknown;
  query?: Record<string, QueryValue>;
};

type EncodedBody = {
  body: BodyInit;
  contentType?: string;
};

export class AventiApiError extends Error {
  readonly name = 'AventiApiError';

  constructor(
    message: string,
    readonly status: number,
    readonly statusText: string,
    readonly body: unknown,
  ) {
    super(message);
  }
}

function missingAuthTokenError(): AventiApiError {
  return new AventiApiError(
    'Authentication required',
    401,
    'Unauthorized',
    { detail: 'Authentication required' },
  );
}

export class AventiApiClient {
  constructor(private readonly options: AventiApiClientOptions) {}

  private buildUrl(path: string, query?: Record<string, QueryValue>): string {
    const baseUrl = this.options.baseUrl.replace(/\/+$/, '');
    const url = new URL(`${baseUrl}${path.startsWith('/') ? path : `/${path}`}`);

    if (query) {
      for (const [key, value] of Object.entries(query)) {
        const values = Array.isArray(value) ? value : [value];
        for (const item of values) {
          if (item === null || item === undefined || item === '') continue;
          url.searchParams.append(key, String(item));
        }
      }
    }

    return url.toString();
  }

  private encodeBody(body: unknown): EncodedBody | undefined {
    if (body === undefined) return undefined;
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    const isUrlSearchParams =
      typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams;
    const isBlob = typeof Blob !== 'undefined' && body instanceof Blob;
    if (typeof body === 'string' || isFormData || isBlob) {
      return { body };
    }
    if (isUrlSearchParams) {
      return { body, contentType: 'application/x-www-form-urlencoded;charset=UTF-8' };
    }
    return { body: JSON.stringify(body), contentType: 'application/json' };
  }

  private async parseResponseBody(response: Response): Promise<unknown> {
    const text = await response.text();
    if (!text) return undefined;

    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }

  private async request<T>(path: string, init: JsonRequestInit = {}): Promise<T> {
    const { auth = 'required', body: rawBody, query, ...requestInit } = init;
    let token: string | null | undefined;
    try {
      token = await this.options.getAccessToken?.();
    } catch (error) {
      if (auth === 'required') {
        throw error;
      }
      token = null;
    }
    if (auth === 'required' && !token) {
      throw missingAuthTokenError();
    }

    const encodedBody = this.encodeBody(rawBody);
    const response = await fetch(this.buildUrl(path, query), {
      ...requestInit,
      body: encodedBody?.body,
      headers: {
        ...(encodedBody?.contentType ? { 'Content-Type': encodedBody.contentType } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });

    if (response.status === 204) {
      return undefined as T;
    }

    const responseBody = await this.parseResponseBody(response);

    if (!response.ok) {
      const detail =
        responseBody && typeof responseBody === 'object' && 'detail' in responseBody
          ? String((responseBody as { detail: unknown }).detail)
          : undefined;
      throw new AventiApiError(
        detail ?? `Aventi API error ${response.status}`,
        response.status,
        response.statusText,
        responseBody,
      );
    }

    return responseBody as T;
  }

  getHealth() {
    return this.request<HealthResponse>(`/v1/health`, { auth: 'optional' });
  }

  bootstrapMe() {
    return this.request<BootstrapMeResponse>(`/v1/me/bootstrap`, { method: 'POST' });
  }

  getMe() {
    return this.request<GetMeResponse>(`/v1/me`);
  }

  updateMyLocation(payload: ProfileLocationPayload) {
    return this.request<UpdateMyLocationResponse>(`/v1/me/location`, {
      method: 'PUT',
      body: payload,
    });
  }

  resolveLocation(payload: LocationResolvePayload) {
    return this.request<LocationResolveResponse>(`/v1/location/resolve`, {
      auth: 'optional',
      method: 'POST',
      body: payload,
    });
  }

  getFeed(payload: FeedRequest) {
    return this.request<FeedResponse>(`/v1/feed`, {
      query: {
        limit: payload.limit ?? 20,
        date: payload.filters.date,
        latitude: payload.latitude,
        longitude: payload.longitude,
        marketCity: payload.marketCity,
        marketState: payload.marketState,
        marketCountry: payload.marketCountry,
        timeOfDay: payload.filters.timeOfDay,
        price: payload.filters.price,
        radiusMiles: payload.filters.radiusMiles,
        cursor: payload.cursor,
        vibes: payload.filters.vibes ?? [],
        categories: payload.filters.categories ?? [],
      },
    });
  }

  refreshFeed(payload: FeedRequest) {
    return this.request<FeedResponse>(`/v1/feed/refresh`, {
      method: 'POST',
      body: payload,
    });
  }

  postSwipe(payload: SwipePayload) {
    return this.request<SwipeResponse>(`/v1/swipes`, {
      method: 'POST',
      body: payload,
    });
  }

  recordFeedImpression(payload: FeedImpressionPayload) {
    return this.request<FeedImpressionResponse>(`/v1/feed/impressions`, {
      method: 'POST',
      body: payload,
    });
  }

  updatePreferences(payload: UserPreferences) {
    return this.request<UpdatePreferencesResponse>(`/v1/me/preferences`, {
      method: 'PUT',
      body: payload,
    });
  }

  resetSeenEvents() {
    return this.request<ResetSeenEventsResponse>(`/v1/me/seen-events/reset`, {
      method: 'POST',
    });
  }

  markMarketSeen(payload: MarketSeenPayload) {
    return this.request<MarketSeenResponse>(`/v1/me/market-seen`, {
      method: 'POST',
      body: payload,
    });
  }

  getEntitlements() {
    return this.request<MembershipEntitlements>(`/v1/membership/entitlements`);
  }

  getAdminDashboard() {
    return this.request<AdminDashboardResponse>(`/v1/admin/dashboard`);
  }

  getAdminSystem() {
    return this.request<AdminSystemResponse>(`/v1/admin/system`);
  }

  getAdminFeedDiagnostic(marketKey: string) {
    return this.request<AdminFeedDiagnosticResponse>(
      `/v1/admin/markets/${encodeURIComponent(marketKey)}/feed-diagnostic`,
    );
  }

  getAdminUserLocations() {
    return this.request<AdminUserLocationsResponse>(`/v1/admin/user-locations`);
  }

  postAdminImportMarketsFromCatalog() {
    return this.request<AdminImportMarketsCatalogResponse>(`/v1/admin/import-markets-from-catalog`, {
      method: 'POST',
    });
  }

  postAdminEnqueueMarketScan(payload: AdminEnqueueMarketScanPayload) {
    return this.request<AdminEnqueueMarketScanResponse>(`/v1/admin/markets/enqueue-scan`, {
      method: 'POST',
      body: payload,
    });
  }

  postAdminSchedulerSmoke(limit = 1) {
    return this.request<AdminSmokeActionResponse>(`/v1/admin/system/scheduler-runs/smoke`, {
      method: 'POST',
      body: { limit },
    });
  }

  postAdminVerificationSmoke(limit = 5) {
    return this.request<AdminSmokeActionResponse>(`/v1/admin/system/verification/smoke`, {
      method: 'POST',
      body: { limit },
    });
  }

  postAdminImageSmoke() {
    return this.request<AdminSmokeActionResponse>(`/v1/admin/system/images/smoke`, {
      method: 'POST',
    });
  }

  postAdminFeedSmoke(payload?: { marketKey?: string | null }) {
    return this.request<AdminSmokeActionResponse>(`/v1/admin/system/feed/smoke`, {
      method: 'POST',
      body: payload ?? {},
    });
  }

  getFavorites() {
    return this.request<FavoritesResponse>(`/v1/favorites`);
  }

  saveFavorite(eventId: string) {
    return this.request<SaveFavoriteResponse>(`/v1/favorites/${eventId}`, {
      method: 'PUT',
    });
  }

  deleteFavorite(eventId: string) {
    return this.request<DeleteFavoriteResponse>(`/v1/favorites/${eventId}`, {
      method: 'DELETE',
    });
  }

  reportEvent(eventId: string, payload: EventReportPayload) {
    return this.request<EventReportResponse>(`/v1/events/${eventId}/report`, {
      method: 'POST',
      body: payload,
    });
  }
}







