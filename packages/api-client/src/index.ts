import type {
  FeedImpressionPayload,
  FeedRequest,
  FeedResponse,
  FavoritesResponse,
  MeProfile,
  MembershipEntitlements,
  ProfileLocationPayload,
  ReportReason,
  SwipePayload,
  UserPreferences,
} from '@aventi/contracts';

export interface AventiApiClientOptions {
  baseUrl: string;
  getAccessToken?: () => Promise<string | null> | string | null;
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
      throw new Error(`Aventi API error ${response.status}`);
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
      ...(payload.filters.timeOfDay ? { timeOfDay: payload.filters.timeOfDay } : {}),
      ...(payload.filters.price ? { price: payload.filters.price } : {}),
      ...(payload.filters.radiusMiles ? { radiusMiles: String(payload.filters.radiusMiles) } : {}),
      ...(payload.cursor ? { cursor: payload.cursor } : {}),
    });
    return this.request<FeedResponse>(`/v1/feed?${search.toString()}`);
  }

  postSwipe(payload: SwipePayload) {
    return this.request<{
      accepted: true;
      remainingFreeSwipes?: number;
      remainingFreePreferenceActions?: number;
    }>(`/v1/swipes`, {
      method: 'POST',
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

  getEntitlements() {
    return this.request<MembershipEntitlements>(`/v1/membership/entitlements`);
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
