export type SwipeAction = 'like' | 'pass';

export type EventVibeTag =
  | 'chill'
  | 'energetic'
  | 'romantic'
  | 'social'
  | 'luxury'
  | 'live-music'
  | 'wellness'
  | 'late-night';

export type ReportReason = 'invalid' | 'cancelled' | 'duplicate' | 'unsafe' | 'other';

export type EventCategory = 'nightlife' | 'dining' | 'concerts' | 'wellness' | 'experiences';

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
}

export interface FeedFilters {
  date: 'today' | 'tomorrow' | 'weekend' | 'week';
  timeOfDay?: 'morning' | 'afternoon' | 'evening' | 'night';
  price?: 'free' | 'paid' | 'any';
  radiusMiles?: number;
  premiumAgeRestriction?: 'all' | '18+' | '21+';
}

export interface FeedRequest {
  cursor?: string;
  limit?: number;
  filters: FeedFilters;
  latitude: number;
  longitude: number;
}

export interface FeedResponse {
  items: EventCard[];
  nextCursor?: string | null;
  fallbackStatus?: 'none' | 'relaxed_filters' | 'insufficient_inventory';
  remainingFreeSwipes?: number;
  remainingFreePreferenceActions?: number;
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
  timezone?: string | null;
}

export interface MeProfile {
  city?: string | null;
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

export const RANKING_CONSTANTS = {
  BASELINE_WEIGHT: 1.0,
  LIKE_MULTIPLIER: 1.1,
  LIKE_BONUS: 0.1,
  PASS_MULTIPLIER: 0.95,
  FREE_PREFERENCE_ACTION_LIMIT_PER_DAY: 10,
  FREE_SWIPE_LIMIT_PER_DAY: 10,
} as const;
