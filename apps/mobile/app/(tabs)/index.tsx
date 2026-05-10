import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { router } from 'expo-router';
import { FlashList, type FlashListRef } from '@shopify/flash-list';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  Pressable,
  Share,
  Text,
  View,
  useWindowDimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type ViewToken,
} from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { EventCard as EventCardModel, FeedFilters, SwipeAction } from '@aventi/contracts';
import { RANKING_CONSTANTS } from '@aventi/contracts';
import { EventCard } from '../../components/EventCard';
import { EventDetailModal } from '../../components/EventDetailModal';
import { FeedActionRail } from '../../components/FeedActionRail';
import { FilterSheet } from '../../components/FilterSheet';
import { GlassPanel } from '../../components/GlassPanel';
import { LoadingConstruct, LoadingProgressBar } from '../../components/LoadingConstruct';
import { Ionicons } from '@expo/vector-icons';

import { aventiApi } from '../../lib/api';
import { useAuthSession } from '../../lib/auth-session';
import { useLocationGate } from '../../lib/location-gate';

function mergeUniqueEvents(existing: EventCardModel[], incoming: EventCardModel[]): EventCardModel[] {
  if (existing.length === 0) return incoming;
  const seen = new Set(existing.map((event) => event.id));
  const appended = incoming.filter((event) => !seen.has(event.id));
  return appended.length > 0 ? [...existing, ...appended] : existing;
}

const WEEKDAY_FORMATTER = new Intl.DateTimeFormat(undefined, { weekday: 'long' });
const MONTH_DAY_FORMATTER = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' });
const DEFAULT_RADIUS_MILES = 25;
const DEFAULT_DISCOVERY_FILTERS: FeedFilters = {
  date: 'week',
  timeOfDay: undefined,
  price: 'any',
  radiusMiles: DEFAULT_RADIUS_MILES,
  vibes: [],
  categories: [],
};

function isSameCalendarDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatEventTiming(startsAt: string, endsAt: string | null | undefined, now: Date): string {
  const start = new Date(startsAt);
  if (Number.isNaN(start.getTime())) return 'Up Next';

  const end = endsAt ? new Date(endsAt) : null;
  const nowMs = now.getTime();
  const startMs = start.getTime();
  const endMs = end && !Number.isNaN(end.getTime()) ? end.getTime() : null;

  if (endMs !== null && nowMs >= endMs) return 'Ended';
  if (startMs <= nowMs) {
    return endMs !== null || startMs > nowMs - 6 * 60 * 60 * 1000 ? 'Live Now' : 'Happening';
  }

  const diffMs = startMs - nowMs;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return 'Starting';
  if (diffMin < 60) return `Starts in ${diffMin}m`;

  const diffHours = Math.round(diffMin / 60);
  if (diffHours < 12 && isSameCalendarDay(start, now)) return `Starts in ${diffHours}h`;

  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (isSameCalendarDay(start, tomorrow)) return 'Tomorrow';

  const diffDays = Math.floor((startMs - new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) / 86_400_000);
  if (diffDays >= 2 && diffDays <= 6) return WEEKDAY_FORMATTER.format(start);

  return MONTH_DAY_FORMATTER.format(start);
}

function formatCategoryFilterLabel(categories: FeedFilters['categories']): string {
  if (!categories || categories.length === 0) return 'All Categories';
  const labels = {
    nightlife: 'Nightlife',
    dining: 'Dining',
    concerts: 'Live Music',
    experiences: 'Arts',
    wellness: 'Wellness',
    comedy: 'Comedy',
    sports: 'Sports',
    outdoors: 'Outdoors',
    markets: 'Markets',
    tech: 'Tech & Talks',
  } as const;
  return categories.length === 1 ? labels[categories[0]] : `${categories.length} Categories`;
}

function formatVibeFilterLabel(vibes: FeedFilters['vibes']): string {
  if (!vibes || vibes.length === 0) return 'All Vibes';
  const labels = {
    chill: 'Chill',
    energetic: 'Energetic',
    intellectual: 'Intellectual',
    romantic: 'Romantic',
    social: 'Social',
    luxury: 'Luxury',
    'live-music': 'Live Music',
    wellness: 'Wellness',
    'late-night': 'Late Night',
    'solo-friendly': 'Solo-Friendly',
    family: 'Family',
    adventurous: 'Adventurous',
    intimate: 'Intimate',
    underground: 'Underground',
  } as const;
  return vibes.length === 1 ? labels[vibes[0]] : `${vibes.length} Vibes`;
}

function formatDateFilterLabel(date: FeedFilters['date']): string {
  return date === 'week'
    ? 'This Week'
    : date === 'weekend'
      ? 'This Weekend'
      : date === 'today'
        ? 'Today'
        : date === 'tomorrow'
          ? 'Tomorrow'
          : date;
}

export default function HomeScreen() {
  const auth = useAuthSession();
  const location = useLocationGate();
  const queryClient = useQueryClient();
  const { height: windowHeight } = useWindowDimensions();
  const listRef = useRef<FlashListRef<EventCardModel>>(null);
  const impressionSeenRef = useRef<Set<string>>(new Set());
  const dismissedIdsRef = useRef<Set<string>>(new Set());
  const mineOnNextFeedRequestRef = useRef(false);
  const autoMineTriggeredRef = useRef(false);
  const autoMineAttemptsRef = useRef(0);
  const AUTO_MINE_MAX_ATTEMPTS = 3;
  const scrollToTopAfterMiningRef = useRef(false);
  const scrollMetricsRef = useRef({
    offsetY: 0,
    contentHeight: 0,
    viewportHeight: 0,
  });
  const footerPullStartedAtEndRef = useRef(false);
  const footerPullStartOffsetRef = useRef(0);
  const viewabilityConfigRef = useRef({
    itemVisiblePercentThreshold: 70,
  });

  const [isManualRefreshing, setIsManualRefreshing] = useState(false);
  const [isMiningRefreshActive, setIsMiningRefreshActive] = useState(false);
  const [isFooterPullPrimed, setIsFooterPullPrimed] = useState(false);
  const [feedCursor, setFeedCursor] = useState<string | null>(null);
  const [feedRefreshToken, setFeedRefreshToken] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<EventCardModel[]>([]);
  const [eventActions, setEventActions] = useState<Partial<Record<string, SwipeAction>>>({});
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const [feedViewportHeight, setFeedViewportHeight] = useState<number>(0);
  const [remainingPreferenceActions, setRemainingPreferenceActions] = useState<number>(
    RANKING_CONSTANTS.FREE_PREFERENCE_ACTION_LIMIT_PER_DAY,
  );
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailEvent, setDetailEvent] = useState<EventCardModel | null>(null);
  const [uiNotice, setUiNotice] = useState<string | null>(null);
  const [filterSheetVisible, setFilterSheetVisible] = useState(false);
  const [filters, setFilters] = useState<FeedFilters>(DEFAULT_DISCOVERY_FILTERS);
  const [nowTick, setNowTick] = useState<number>(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNowTick(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

  const appUnlocked = auth.isReady && auth.isAuthenticated;
  const serverCallsEnabled = appUnlocked;
  const canPersistServerActions = auth.isAuthenticated;

  const bootstrapQuery = useQuery({
    queryKey: ['me', 'bootstrap', auth.session?.user.id ?? 'no-session'],
    enabled: serverCallsEnabled,
    queryFn: () => aventiApi.bootstrapMe(),
    staleTime: 60_000,
  });

  const entitlementsQuery = useQuery({
    queryKey: ['membership', 'entitlements', auth.session?.user.id ?? 'no-session'],
    enabled: serverCallsEnabled && auth.isFullAccount,
    queryFn: () => aventiApi.getEntitlements(),
    staleTime: 60_000,
  });
  const isPremium = entitlementsQuery.data?.isPremium ?? false;

  const feedQuery = useQuery({
    queryKey: [
      'feed',
      auth.session?.user.id ?? 'no-session',
      location.effectiveLocation?.latitude,
      location.effectiveLocation?.longitude,
      location.effectiveLocation?.city,
      filters.date,
      filters.timeOfDay,
      filters.price,
      filters.radiusMiles,
      (filters.vibes ?? []).join(','),
      (filters.categories ?? []).join(','),
      feedCursor,
      feedRefreshToken,
    ],
    enabled: appUnlocked && Boolean(location.effectiveLocation),
    queryFn: async () => {
      const request = {
        latitude: location.effectiveLocation!.latitude,
        longitude: location.effectiveLocation!.longitude,
        marketCity: location.effectiveLocation?.city ?? undefined,
        marketState: location.effectiveLocation?.state ?? undefined,
        marketCountry: location.effectiveLocation?.country ?? undefined,
        limit: 20,
        filters,
        cursor: feedCursor ?? undefined,
      };
      const timeoutMs = 30_000;
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('Feed request timed out after 30s')), timeoutMs);
      });
      const apiPromise = mineOnNextFeedRequestRef.current
        ? aventiApi.refreshFeed(request)
        : aventiApi.getFeed(request);
      if (mineOnNextFeedRequestRef.current) {
        mineOnNextFeedRequestRef.current = false;
      }
      const result = await Promise.race([apiPromise, timeoutPromise]);
      return result;
    },
    staleTime: 15_000,
    refetchInterval: (query) => {
      const status = query.state.data?.inventoryStatus;
      const itemCount = query.state.data?.items?.length ?? 0;
      return itemCount === 0 && (status === 'warming' || status === 'targeted_warming') ? 5_000 : false;
    },
  });

  useEffect(() => {
    if (!appUnlocked || location.status === 'checking') return;
    if (!location.effectiveLocation) {
      router.replace('/onboarding/location');
    }
  }, [appUnlocked, location.effectiveLocation, location.status]);

  useEffect(() => {
    setFeedCursor(null);
    setNextCursor(null);
    setTimelineEvents([]);
    setEventActions({});
    setActiveEventId(null);
    setDetailVisible(false);
    setDetailEvent(null);
    impressionSeenRef.current.clear();
    dismissedIdsRef.current.clear();
    autoMineAttemptsRef.current = 0;
    listRef.current?.scrollToOffset({ offset: 0, animated: false });
  }, [
    auth.session?.user.id,
    location.effectiveLocation?.latitude,
    location.effectiveLocation?.longitude,
    location.isTravelModeActive,
    filters.date,
    filters.timeOfDay,
    filters.price,
    filters.radiusMiles,
    (filters.vibes ?? []).join(','),
    (filters.categories ?? []).join(','),
  ]);

  useEffect(() => {
    if (!feedQuery.data) return;
    const remaining =
      feedQuery.data.remainingFreePreferenceActions ?? feedQuery.data.remainingFreeSwipes;
    if (typeof remaining === 'number') {
      setRemainingPreferenceActions(remaining);
    }
    setNextCursor(feedQuery.data.nextCursor ?? null);
    setTimelineEvents((previous) => {
      const items = feedCursor === null ? feedQuery.data.items : mergeUniqueEvents(previous, feedQuery.data.items);
      const filtered = items.filter((event) => !dismissedIdsRef.current.has(event.id));
      if (filtered.length > 0) {
        autoMineTriggeredRef.current = false;
        autoMineAttemptsRef.current = 0;
      }
      return filtered;
    });
  }, [feedCursor, feedQuery.data]);

  useEffect(() => {
    const inventoryStatus = feedQuery.data?.inventoryStatus;
    const hasVisibleEvents = timelineEvents.length > 0 || (feedQuery.data?.items?.length ?? 0) > 0;

    if (inventoryStatus === 'targeted_warming') {
      setIsMiningRefreshActive(true);
      return;
    }

    if (inventoryStatus === 'warming' && !hasVisibleEvents) {
      setIsMiningRefreshActive(true);
      return;
    }

    setIsMiningRefreshActive(false);
    autoMineTriggeredRef.current = false;
  }, [feedQuery.data?.inventoryStatus, feedQuery.data?.items?.length, timelineEvents.length]);

  useEffect(() => {
    if (
      feedQuery.data?.inventoryStatus === 'warming' &&
      feedQuery.data?.items?.length === 0 &&
      !feedQuery.isFetching &&
      !mineOnNextFeedRequestRef.current &&
      !autoMineTriggeredRef.current &&
      timelineEvents.length === 0 &&
      autoMineAttemptsRef.current < AUTO_MINE_MAX_ATTEMPTS
    ) {
      autoMineTriggeredRef.current = true;
      autoMineAttemptsRef.current += 1;
      mineOnNextFeedRequestRef.current = true;
      void feedQuery.refetch();
    }
  }, [feedQuery.data?.inventoryStatus, feedQuery.data?.items?.length, feedQuery.isFetching, timelineEvents.length]);

  useEffect(() => {
    if (!isManualRefreshing || feedQuery.isFetching) return;
    setIsManualRefreshing(false);
  }, [feedQuery.isFetching, isManualRefreshing]);

  useEffect(() => {
    if (!scrollToTopAfterMiningRef.current || feedQuery.isFetching) {
      return;
    }
    scrollToTopAfterMiningRef.current = false;
    listRef.current?.scrollToOffset({ offset: 0, animated: true });
  }, [feedQuery.isFetching]);

  useEffect(() => {
    if (nextCursor || isManualRefreshing || isMiningRefreshActive || feedQuery.isFetching) {
      footerPullStartedAtEndRef.current = false;
      footerPullStartOffsetRef.current = 0;
      setIsFooterPullPrimed(false);
    }
  }, [feedQuery.isFetching, isManualRefreshing, isMiningRefreshActive, nextCursor]);

  useEffect(() => {
    if (feedQuery.isFetching || !feedQuery.isError) return;
    setIsMiningRefreshActive(false);
  }, [feedQuery.isError, feedQuery.isFetching]);

  useEffect(() => {
    if (!uiNotice) return;
    const timer = setTimeout(() => setUiNotice(null), 3500);
    return () => clearTimeout(timer);
  }, [uiNotice]);

  const activeEvent = useMemo(
    () => timelineEvents.find((event) => event.id === activeEventId) ?? timelineEvents[0] ?? null,
    [activeEventId, timelineEvents],
  );

  const pageHeight = Math.max(280, Math.floor(feedViewportHeight || windowHeight * 0.58));

  const swipeMutation = useMutation({
    mutationFn: (payload: Parameters<typeof aventiApi.postSwipe>[0]) => aventiApi.postSwipe(payload),
    onSuccess: (result) => {
      const remaining = result.remainingFreePreferenceActions ?? result.remainingFreeSwipes;
      if (typeof remaining === 'number') {
        setRemainingPreferenceActions(remaining);
      }
    },
    onError: () => {
      setUiNotice('Preference action applied locally, but Aventi could not sync it to the server.');
    },
  });

  const [upgradePromptVisible, setUpgradePromptVisible] = useState(false);
  const UPGRADE_PROMPT_THRESHOLD = 3;
  const UPGRADE_PROMPT_STORAGE_KEY = 'aventi_upgrade_prompt_dismissed';

  const favoriteMutation = useMutation({
    mutationFn: (eventId: string) => aventiApi.saveFavorite(eventId),
    onSuccess: async () => {
      void queryClient.invalidateQueries({ queryKey: ['favorites'] });

      // Show soft upgrade prompt for guest users after threshold saves
      if (auth.isAnonymousUser) {
        try {
          const dismissed = await AsyncStorage.getItem(UPGRADE_PROMPT_STORAGE_KEY);
          if (dismissed === 'true') return;

          const favoritesData = queryClient.getQueryData<{ items: string[] }>(['favorites', auth.session?.user.id ?? 'no-session']);
          const savedCount = favoritesData?.items?.length ?? 0;

          if (savedCount >= UPGRADE_PROMPT_THRESHOLD) {
            setUpgradePromptVisible(true);
          }
        } catch {
          // Ignore storage errors
        }
      }
    },
    onError: () => {
      setUiNotice('Could not save favorite right now.');
    },
  });

  const impressionMutation = useMutation({
    mutationFn: (payload: Parameters<typeof aventiApi.recordFeedImpression>[0]) =>
      aventiApi.recordFeedImpression(payload),
  });

  const headerLabel = useMemo(() => {
    if (!appUnlocked) return 'Choose Your Mode';
    if (location.status === 'checking' && !location.effectiveLocation) return 'Checking Location';
    if (!location.effectiveLocation) return 'Location Required';
    if (feedQuery.isLoading && timelineEvents.length === 0) return 'Synthesizing Feed';
    if (feedQuery.isError && timelineEvents.length === 0) return 'Feed Unavailable';
    if (timelineEvents.length === 0) return 'No Events In Feed';
    return 'Tonight in Motion';
  }, [
    appUnlocked,
    feedQuery.isError,
    feedQuery.isLoading,
    location.effectiveLocation,
    location.status,
    timelineEvents.length,
  ]);

  const handleEventAction = useCallback(
    async (event: EventCardModel, action: SwipeAction, position: number) => {
      if (eventActions[event.id]) return;
      if (!isPremium && remainingPreferenceActions <= 0) {
        setUiNotice('Free preference action limit reached. Upgrade to Unlimited for unrestricted curation.');
        return;
      }

      setEventActions((previous) => ({ ...previous, [event.id]: action }));
      if (!isPremium) {
        setRemainingPreferenceActions((value) => Math.max(0, value - 1));
      }

      if (action === 'pass') {
        dismissedIdsRef.current.add(event.id);
        setTimelineEvents((previous) => previous.filter((candidate) => candidate.id !== event.id));
        if (detailEvent?.id === event.id) {
          setDetailVisible(false);
        }
      }

      if (action === 'like') {
        if (canPersistServerActions) {
          favoriteMutation.mutate(event.id);
        } else {
          auth.requireSessionBackedGuestOrAccount('favorites');
          setUiNotice('Start a guest session or sign in to persist Favorites.');
        }
      }

      if (!canPersistServerActions) {
        return;
      }

      swipeMutation.mutate({
        eventId: event.id,
        action,
        surfacedAt: new Date().toISOString(),
        position,
        vibes: event.vibes,
      });
    },
    [
      auth,
      canPersistServerActions,
      detailEvent?.id,
      eventActions,
      favoriteMutation,
      isPremium,
      remainingPreferenceActions,
      swipeMutation,
    ],
  );

  const handleShareEvent = useCallback(async (event: EventCardModel) => {
    try {
      await Share.share({
        message: `${event.title} at ${event.venueName}${event.bookingUrl ? `\n${event.bookingUrl}` : ''}`,
      });
    } catch {
      setUiNotice('Could not open the share sheet right now.');
    }
  }, []);

  const handleLoadMore = useCallback(() => {
    if (!appUnlocked || !location.effectiveLocation) return;
    if (feedQuery.isFetching) return;
    if (isManualRefreshing || isMiningRefreshActive) return;
    if (!nextCursor) return;
    if (feedCursor === nextCursor) return;
    setFeedCursor(nextCursor);
  }, [
    appUnlocked,
    feedCursor,
    feedQuery.isFetching,
    isManualRefreshing,
    isMiningRefreshActive,
    location.effectiveLocation,
    nextCursor,
  ]);

  const handleRefreshFeed = useCallback((options?: { preservePosition?: boolean }) => {
    if (!appUnlocked || !location.effectiveLocation) return;

    setIsManualRefreshing(true);
    impressionSeenRef.current.clear();
    mineOnNextFeedRequestRef.current = serverCallsEnabled;
    if (serverCallsEnabled) {
      setIsMiningRefreshActive(true);
    }
    footerPullStartedAtEndRef.current = false;
    footerPullStartOffsetRef.current = 0;
    setIsFooterPullPrimed(false);
    scrollToTopAfterMiningRef.current = Boolean(options?.preservePosition);
    if (!options?.preservePosition) {
      listRef.current?.scrollToOffset({ offset: 0, animated: true });
    }
    setFeedRefreshToken((value) => value + 1);
    if (feedCursor !== null) {
      setFeedCursor(null);
    }
  }, [
    appUnlocked,
    feedCursor,
    location.effectiveLocation,
    serverCallsEnabled,
  ]);

  const handleResetSeenEvents = useCallback(async () => {
    if (!serverCallsEnabled) return;
    try {
      await aventiApi.resetSeenEvents();
      handleRefreshFeed();
    } catch (err) {
      console.warn('Failed to reset seen events', err);
    }
  }, [serverCallsEnabled, handleRefreshFeed]);

  const handleClearFilters = useCallback(() => {
    setFilters(DEFAULT_DISCOVERY_FILTERS);
    setFilterSheetVisible(false);
  }, []);

  const isNearFeedEnd = useCallback((metrics: { offsetY: number; contentHeight: number; viewportHeight: number }) => {
    const maxOffset = Math.max(0, metrics.contentHeight - metrics.viewportHeight);
    return metrics.contentHeight > 0 && metrics.offsetY >= maxOffset - 24;
  }, []);

  const readScrollMetrics = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const metrics = {
      offsetY: event.nativeEvent.contentOffset.y,
      contentHeight: event.nativeEvent.contentSize.height,
      viewportHeight: event.nativeEvent.layoutMeasurement.height,
    };
    scrollMetricsRef.current = metrics;
    return metrics;
  }, []);

  const handleFeedScroll = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      const metrics = readScrollMetrics(event);
      if (isFooterPullPrimed && !isNearFeedEnd(metrics)) {
        footerPullStartedAtEndRef.current = false;
        setIsFooterPullPrimed(false);
      }
    },
    [isFooterPullPrimed, isNearFeedEnd, readScrollMetrics],
  );

  const handleFeedScrollBeginDrag = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      const metrics = readScrollMetrics(event);
      const canPrime =
        !nextCursor &&
        timelineEvents.length > 0 &&
        !feedQuery.isFetching &&
        !isManualRefreshing &&
        !isMiningRefreshActive &&
        isNearFeedEnd(metrics);

      footerPullStartedAtEndRef.current = canPrime;
      footerPullStartOffsetRef.current = metrics.offsetY;
      setIsFooterPullPrimed(canPrime);
    },
    [
      feedQuery.isFetching,
      isManualRefreshing,
      isMiningRefreshActive,
      isNearFeedEnd,
      nextCursor,
      readScrollMetrics,
      timelineEvents.length,
    ],
  );

  const handleFeedScrollEndDrag = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      const metrics = readScrollMetrics(event);
      const stayedNearEnd = metrics.offsetY >= footerPullStartOffsetRef.current - 12 && isNearFeedEnd(metrics);
      const shouldTrigger = footerPullStartedAtEndRef.current && stayedNearEnd;

      footerPullStartedAtEndRef.current = false;
      footerPullStartOffsetRef.current = 0;
      setIsFooterPullPrimed(false);

      if (shouldTrigger) {
        handleRefreshFeed({ preservePosition: true });
      }
    },
    [handleRefreshFeed, isNearFeedEnd, readScrollMetrics],
  );

  const handleOpenProfile = () => {
    router.push('/profile');
  };

  const handleOpenLocationSetup = () => {
    router.push('/onboarding/location');
  };

  const handleOpenFavorites = () => {
    if (!auth.requireSessionBackedGuestOrAccount('favorites')) {
      setUiNotice('Start a guest session or sign in to open Favorites.');
      return;
    }
    router.push('/favorites');
  };

  const handleDismissUpgradePrompt = async () => {
    setUpgradePromptVisible(false);
    try {
      await AsyncStorage.setItem(UPGRADE_PROMPT_STORAGE_KEY, 'true');
    } catch {
      // Ignore storage errors
    }
  };

  const handleUpgradeFromPrompt = () => {
    setUpgradePromptVisible(false);
    auth.openAuthPrompt('sync');
  };

  const statusLine = !appUnlocked
    ? auth.guestAuthError ?? 'Start a guest session or sign in to begin discovery'
    : !location.effectiveLocation
      ? location.errorMessage ?? 'Choose device or travel coordinates to initialize your local feed'
      : feedQuery.isLoading && timelineEvents.length === 0
        ? 'Synthesizing your local event feed...'
        : feedQuery.isError && timelineEvents.length === 0
          ? 'Could not load the feed from FastAPI. Check EXPO_PUBLIC_API_BASE_URL and backend status.'
          : `${remainingPreferenceActions} free preference actions left today • ${location.effectiveLocation.label}`;

  const onViewableItemsChanged = useCallback(
    ({ viewableItems }: { viewableItems: ViewToken[] }) => {
      const visible = viewableItems.find((item) => item.isViewable)?.item as EventCardModel | undefined;
      if (!visible) return;
      setActiveEventId(visible.id);

      if (impressionSeenRef.current.has(visible.id)) {
        return;
      }
      impressionSeenRef.current.add(visible.id);

      if (!canPersistServerActions) {
        return;
      }

      const visibleToken = viewableItems.find(
        (token) => token.isViewable && (token.item as EventCardModel | undefined)?.id === visible.id,
      );
      impressionMutation.mutate({
        eventId: visible.id,
        servedAt: new Date().toISOString(),
        position: typeof visibleToken?.index === 'number' ? visibleToken.index : undefined,
        filters: {
          date: filters.date,
          timeOfDay: filters.timeOfDay ?? null,
          price: filters.price,
          radiusMiles: filters.radiusMiles,
          vibes: filters.vibes ?? [],
          categories: filters.categories ?? [],
          travelMode: location.isTravelModeActive,
          latitude: location.effectiveLocation?.latitude ?? null,
          longitude: location.effectiveLocation?.longitude ?? null,
        },
      });
    },
    [
      canPersistServerActions,
      filters.date,
      filters.price,
      filters.radiusMiles,
      filters.timeOfDay,
      filters.vibes,
      filters.categories,
      impressionMutation,
      location.effectiveLocation?.latitude,
      location.effectiveLocation?.longitude,
      location.isTravelModeActive,
    ],
  );

  const renderFeedItem = useCallback(
    ({ item, index }: { item: EventCardModel; index: number }) => {
      const action = eventActions[item.id];
      const preferenceLimitReached = !isPremium && remainingPreferenceActions <= 0 && !action;
      return (
        <View style={{ height: pageHeight }} className="pb-4">
          <View className="flex-1">
            <EventCard event={item} />

            <View className="absolute top-3 left-3 px-3 py-1 rounded-full border border-white/10 bg-black/45">
              <Text className="text-[10px] uppercase tracking-[1.2px] text-white/80">
                {formatEventTiming(item.startsAt, item.endsAt, new Date(nowTick))}
              </Text>
            </View>

            <View className="absolute right-3 bottom-6">
              <FeedActionRail
                saved={action === 'like'}
                disabled={preferenceLimitReached}
                onPass={() => {
                  void handleEventAction(item, 'pass', index);
                }}
                onSave={() => {
                  void handleEventAction(item, 'like', index);
                }}
                onInfo={() => {
                  setDetailEvent(item);
                  setDetailVisible(true);
                }}
                onShare={() => {
                  void handleShareEvent(item);
                }}
              />
            </View>
          </View>
        </View>
      );
    },
    [
      eventActions,
      handleEventAction,
      handleShareEvent,
      isPremium,
      nowTick,
      pageHeight,
      remainingPreferenceActions,
    ],
  );

  const listFooter = useMemo(() => {
    if (isManualRefreshing && feedQuery.isFetching && timelineEvents.length > 0) {
      return (
        <View className="items-center pt-4 pb-8">
          <View className="w-full items-center rounded-[20px] border border-white/10 bg-white/5 px-6 py-5">
            <Text className="text-center text-[11px] font-bold uppercase tracking-[1.4px] text-[#A67CFF]">
              {serverCallsEnabled ? 'Mining New Events...' : 'Refreshing Feed...'}
            </Text>
            <Text className="mt-1.5 text-center text-[10px] uppercase tracking-[1px] text-white/40">
              {serverCallsEnabled
                ? `Searching ${location.effectiveLocation?.city ?? 'your area'} for fresh events`
                : 'Reloading your current guest feed'}
            </Text>
            <View className="mt-3">
              <LoadingProgressBar width={180} />
            </View>
          </View>
        </View>
      );
    }
    if (feedQuery.isFetching && timelineEvents.length > 0) {
      return (
        <View className="pt-2 pb-6">
          <Text className="text-center text-[11px] uppercase tracking-[1.4px] text-white/55">
            Loading more events...
          </Text>
        </View>
      );
    }
    if (!nextCursor && timelineEvents.length > 0) {
      if (feedQuery.data?.inventoryStatus === 'targeted_warming') {
        return (
          <View className="items-center pt-4 pb-8">
            <View className="w-full items-center rounded-[20px] border border-white/10 bg-white/5 px-6 py-5">
              <Text className="text-center text-[11px] font-bold uppercase tracking-[1.4px] text-[#A67CFF]">
                Mining Filtered Events...
              </Text>
              <Text className="text-center text-[10px] uppercase tracking-[1px] text-white/40 mt-1.5">
                {`Searching ${location.effectiveLocation?.city ?? 'your area'} for events matching your filters`}
              </Text>
              <View className="mt-3">
                <LoadingProgressBar width={180} />
              </View>
            </View>
          </View>
        );
      }
      return (
        <View className="items-center pt-4 pb-8">
          <View className="w-full items-center rounded-[20px] border border-white/10 bg-white/5 px-6 py-6">
            <Ionicons
              name={isFooterPullPrimed ? 'arrow-up-circle-outline' : 'chevron-down'}
              size={22}
              color={isFooterPullPrimed ? '#A67CFF' : 'rgba(255,255,255,0.35)'}
            />
            <Text className="mt-3 text-center text-[11px] uppercase tracking-[1.4px] text-white/45">
              End of current feed
            </Text>
            <Text className="mt-1.5 text-center text-[10px] uppercase tracking-[1px] text-white/55">
              {isFooterPullPrimed
                ? serverCallsEnabled
                  ? 'Release to mine more events'
                  : 'Release to refresh feed'
                : serverCallsEnabled
                  ? 'Pull down to mine more events'
                  : 'Pull down to refresh feed'}
            </Text>
            {isFooterPullPrimed ? (
              <View className="mt-4 h-1 w-full max-w-[220px] overflow-hidden rounded-full bg-white/10">
                <View className="h-full w-full rounded-full bg-[#A67CFF]" />
              </View>
            ) : null}
          </View>
        </View>
      );
    }
    return null;
  }, [
    feedQuery.data?.inventoryStatus,
    feedQuery.isFetching,
    isFooterPullPrimed,
    isManualRefreshing,
    location.effectiveLocation?.city,
    nextCursor,
    serverCallsEnabled,
    timelineEvents.length,
  ]);

  const showMiningBanner = timelineEvents.length > 0 && isManualRefreshing && feedQuery.isFetching;
  const hasActiveFilters =
    filters.date !== 'week' ||
    filters.timeOfDay !== undefined ||
    filters.price !== 'any' ||
    filters.radiusMiles !== DEFAULT_RADIUS_MILES ||
    (filters.vibes?.length ?? 0) > 0 ||
    (filters.categories?.length ?? 0) > 0;
  const filterChips = [
    { label: 'Filter', onPress: () => setFilterSheetVisible(true) },
    ...(hasActiveFilters
      ? [
          ...(filters.date !== 'week'
            ? [{ label: formatDateFilterLabel(filters.date), onPress: () => setFilterSheetVisible(true) }]
            : []),
          ...(filters.timeOfDay
            ? [{
                label: filters.timeOfDay.charAt(0).toUpperCase() + filters.timeOfDay.slice(1),
                onPress: () => setFilterSheetVisible(true),
              }]
            : []),
          ...(filters.price !== 'any'
            ? [{ label: filters.price === 'free' ? 'Free' : 'Paid', onPress: () => setFilterSheetVisible(true) }]
            : []),
          ...((filters.vibes?.length ?? 0) > 0
            ? [{ label: formatVibeFilterLabel(filters.vibes), onPress: () => setFilterSheetVisible(true) }]
            : []),
          ...((filters.categories?.length ?? 0) > 0
            ? [{ label: formatCategoryFilterLabel(filters.categories), onPress: () => setFilterSheetVisible(true) }]
            : []),
          ...(filters.radiusMiles !== DEFAULT_RADIUS_MILES
            ? [{
                label: `Within ${filters.radiusMiles} mi`,
                onPress: () => setFilterSheetVisible(true),
                premium: !isPremium,
              }]
            : []),
        ]
      : []),
    {
      label: isPremium ? '21+' : '21+ (Premium)',
      onPress: () => {
        if (!isPremium) {
          auth.openAuthPrompt('premium');
        }
      },
    },
  ];

  return (
    <View className="flex-1 px-4 pt-14 bg-black">
      <View className="flex-row justify-between items-center mb-2">
        <View>
          <Text className="text-xs uppercase tracking-[3px] text-white/55">Aventi</Text>
          <Text className="mt-2 text-2xl font-bold uppercase tracking-[2px] text-white">
            {headerLabel}
          </Text>
        </View>
        <View className="flex-row gap-3">
          <Pressable
            onPress={handleOpenFavorites}
            className="justify-center items-center w-10 h-10 rounded-full bg-white/10 active:scale-95"
          >
            <Ionicons name="heart-outline" size={24} color="white" />
          </Pressable>
          <Pressable
            onPress={handleOpenProfile}
            className="justify-center items-center w-10 h-10 rounded-full bg-white/10 active:scale-95"
          >
            <Ionicons name="person-outline" size={22} color="white" />
          </Pressable>
        </View>
      </View>

      <View className="flex-row flex-wrap gap-2 mb-4">
        {filterChips.map((chip, index) => (
          <Pressable
            key={`${chip.label}-${index}`}
            onPress={chip.onPress}
            className={`rounded-full border px-3 py-2 active:scale-95 ${
              chip.premium ? 'border-[#A67CFF]/30 bg-[#A67CFF]/10' : 'border-white/10 bg-white/5'
            }`}
          >
            <Text className={`text-[11px] uppercase tracking-[1.2px] ${chip.premium ? 'text-[#A67CFF]/80' : 'text-white/75'}`}>
              {chip.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {showMiningBanner ? (
        <View className="mb-4 rounded-[20px] border border-white/10 bg-white/5 px-4 py-3">
          <View className="flex-row gap-3 items-center">
            <LoadingProgressBar width={88} />
            <View className="flex-1">
              <Text className="text-[11px] font-bold uppercase tracking-[1.4px] text-[#A67CFF]">
                {serverCallsEnabled ? 'Mining New Events' : 'Refreshing Feed'}
              </Text>
              <Text className="mt-1 text-[11px] leading-4 text-white/55">
                {serverCallsEnabled
                  ? feedQuery.isFetching
                    ? `Refreshing ${location.effectiveLocation?.city ?? 'your area'} and queueing a fresh scan.`
                    : `Aventi is loading more live events for ${location.effectiveLocation?.city ?? 'your area'}.`
                  : 'Reloading the current guest feed.'}
              </Text>
            </View>
          </View>
        </View>
      ) : null}

      {upgradePromptVisible ? (
        <View className="mb-4 rounded-[20px] border border-amber-200/20 bg-amber-400/10 px-4 py-4">
          <View className="flex-row gap-3 items-start">
            <View className="flex-1">
              <Text className="text-[12px] font-semibold uppercase tracking-[1.4px] text-amber-100/95">
                Love these picks?
              </Text>
              <Text className="mt-1.5 text-sm leading-5 text-white/85">
                Create a free account to keep your {UPGRADE_PROMPT_THRESHOLD}+ favorites forever across devices.
              </Text>
              <View className="flex-row gap-2 mt-3">
                <Pressable
                  onPress={handleUpgradeFromPrompt}
                  className="rounded-xl border border-amber-200/30 bg-amber-400/20 px-4 py-2.5 active:scale-95"
                >
                  <Text className="text-xs font-semibold uppercase tracking-[1.2px] text-amber-100">
                    Create Free Account
                  </Text>
                </Pressable>
                <Pressable
                  onPress={handleDismissUpgradePrompt}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 active:scale-95"
                >
                  <Text className="text-xs font-semibold uppercase tracking-[1.2px] text-white/65">
                    Keep Browsing
                  </Text>
                </Pressable>
              </View>
            </View>
          </View>
        </View>
      ) : null}

      <View
        className="flex-1"
        onLayout={(event) => {
          const nextHeight = Math.max(0, Math.floor(event.nativeEvent.layout.height));
          if (nextHeight && nextHeight !== feedViewportHeight) {
            setFeedViewportHeight(nextHeight);
          }
        }}
      >
        {!appUnlocked ? (
          !auth.isReady ? (
            <LoadingConstruct label="Preparing guest access" />
          ) : (
            <GlassPanel>
              <Text className="text-sm uppercase tracking-[2px] text-white/65">Guest Access Required</Text>
              <Text className="mt-2 text-lg font-semibold text-white">
                Start a Supabase guest session or sign in to continue.
              </Text>
              <Text className="mt-2 text-sm leading-5 text-white/70">
                {auth.guestAuthError ??
                  'Guest access now requires a Supabase anonymous session or a full account.'}
              </Text>
              <Pressable
                onPress={() => auth.openAuthPrompt('welcome')}
                className="self-start px-4 py-3 mt-4 rounded-full border border-white/15 bg-white/10 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                  Open Guest Auth
                </Text>
              </Pressable>
            </GlassPanel>
          )
        ) : location.status === 'checking' && !location.effectiveLocation ? (
          <LoadingConstruct label="Checking location access before loading Aventi" />
        ) : !location.effectiveLocation ? (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">Location Setup</Text>
            <Text className="mt-2 text-lg font-semibold text-white">Finish onboarding to unlock your local feed.</Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              Grant device location or enter Travel Mode coordinates for testing. Either path unlocks discovery now.
            </Text>
            <Pressable
              onPress={handleOpenLocationSetup}
              className="self-start px-4 py-3 mt-4 rounded-full border border-white/15 bg-white/10 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                Open Location Setup
              </Text>
            </Pressable>
          </GlassPanel>
        ) : feedQuery.isLoading && timelineEvents.length === 0 ? (
          <LoadingConstruct
            label={`Synthesizing your ${location.effectiveLocation?.city ?? 'city'} feed from Aventi API`}
          />
        ) : feedQuery.isError && timelineEvents.length === 0 ? (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">Feed Error</Text>
            <Text className="mt-2 text-lg font-semibold text-white">
              {(feedQuery.error as Error)?.message?.includes('timed out')
                ? 'Feed request timed out.'
                : 'FastAPI feed is unavailable.'}
            </Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              {(feedQuery.error as Error)?.message?.includes('timed out')
                ? 'The backend took too long to respond. Check if the server is running and reachable.'
                : 'Start the backend (`pnpm backend:dev`) and ensure `EXPO_PUBLIC_API_BASE_URL` points to it.'}
            </Text>
            <Pressable
              onPress={() => feedQuery.refetch()}
              className="self-start px-4 py-3 mt-4 rounded-full border border-white/15 bg-white/10 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Retry</Text>
            </Pressable>
          </GlassPanel>
        ) : timelineEvents.length > 0 ? (
          <FlashList
            ref={listRef}
            data={timelineEvents}
            renderItem={renderFeedItem}
            keyExtractor={(item) => item.id}
            pagingEnabled
            snapToInterval={pageHeight}
            decelerationRate="fast"
            disableIntervalMomentum
            showsVerticalScrollIndicator={false}
            onEndReached={handleLoadMore}
            onEndReachedThreshold={0.7}
            onScroll={handleFeedScroll}
            onScrollBeginDrag={handleFeedScrollBeginDrag}
            onScrollEndDrag={handleFeedScrollEndDrag}
            onViewableItemsChanged={onViewableItemsChanged}
            viewabilityConfig={viewabilityConfigRef.current}
            ListFooterComponent={listFooter}
            onRefresh={handleRefreshFeed}
            refreshing={isManualRefreshing}
            progressViewOffset={24}
            overScrollMode="always"
            scrollEventThrottle={16}
          />
        ) : feedQuery.data?.items && feedQuery.data.items.length > 0 ? (
          <FlashList
            ref={listRef}
            data={feedQuery.data.items}
            renderItem={renderFeedItem}
            keyExtractor={(item) => item.id}
            pagingEnabled
            snapToInterval={pageHeight}
            decelerationRate="fast"
            disableIntervalMomentum
            showsVerticalScrollIndicator={false}
            onEndReached={handleLoadMore}
            onEndReachedThreshold={0.7}
            onScroll={handleFeedScroll}
            onScrollBeginDrag={handleFeedScrollBeginDrag}
            onScrollEndDrag={handleFeedScrollEndDrag}
            onViewableItemsChanged={onViewableItemsChanged}
            viewabilityConfig={viewabilityConfigRef.current}
            ListFooterComponent={listFooter}
            onRefresh={handleRefreshFeed}
            refreshing={isManualRefreshing}
            progressViewOffset={24}
            overScrollMode="always"
            scrollEventThrottle={16}
          />
        ) : feedQuery.data?.inventoryStatus === 'targeted_warming' ? (
          <LoadingConstruct
            label={`Mining events in ${location.effectiveLocation?.city ?? 'your area'} that match your filters...\nAuto-loading when ready`}
            showProgress={true}
          />
        ) : feedQuery.data?.inventoryStatus === 'warming' ? (
          <LoadingConstruct
            label={`Mining events in ${location.effectiveLocation?.city ?? 'your area'}...\nAuto-loading when ready`}
            showProgress={true}
          />
        ) : feedQuery.data?.inventoryStatus === 'no_matches' ? (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">No Matches</Text>
            <Text className="mt-2 text-lg font-semibold text-white">
              No events match your current filters in {location.effectiveLocation?.city ?? 'this area'}.
            </Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              Aventi already checked for more events matching these constraints. Try editing or clearing filters to widen the search.
            </Text>
            <View className="flex-row gap-3 mt-4">
              <Pressable
                onPress={() => setFilterSheetVisible(true)}
                className="px-4 py-3 rounded-full border border-white/15 bg-white/5 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  Edit Filters
                </Text>
              </Pressable>
              <Pressable
                onPress={handleClearFilters}
                className="rounded-full border border-[#A67CFF]/40 bg-[#A67CFF]/10 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-[#A67CFF]">
                  Clear Filters
                </Text>
              </Pressable>
            </View>
          </GlassPanel>
        ) : (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">Feed Complete</Text>
            <Text className="mt-2 text-lg font-semibold text-white">
              {'You reached the end of the current event stream.'}
            </Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              Aventi auto-loads more events as you scroll. You can also refresh to start from the top.
            </Text>
            <View className="flex-row gap-3 mt-4">
              <Pressable
                onPress={() => handleRefreshFeed()}
                className="px-4 py-3 rounded-full border border-white/15 bg-white/5 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  Refresh Feed
                </Text>
              </Pressable>
              <Pressable
                onPress={handleResetSeenEvents}
                className="rounded-full border border-[#A67CFF]/40 bg-[#A67CFF]/10 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-[#A67CFF]">
                  Reset Seen
                </Text>
              </Pressable>
            </View>
            {feedCursor ? (
              <Text className="mt-3 text-[11px] uppercase tracking-[1.2px] text-white/55">
                Current page cursor: {feedCursor}
              </Text>
            ) : null}
          </GlassPanel>
        )}
      </View>

      <EventDetailModal
        event={detailEvent ?? activeEvent}
        visible={detailVisible}
        onClose={() => setDetailVisible(false)}
      />

      <FilterSheet
        visible={filterSheetVisible}
        filters={filters}
        onClose={() => setFilterSheetVisible(false)}
        onApply={(newFilters) => {
          setFilters(newFilters);
        }}
        isPremium={isPremium}
      />
    </View>
  );
}
