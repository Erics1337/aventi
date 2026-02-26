import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { router } from 'expo-router';
import { FlashList, type FlashListRef } from '@shopify/flash-list';
import {
  Pressable,
  Share,
  Text,
  View,
  useWindowDimensions,
  type ViewToken,
} from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { EventCard as EventCardModel, FeedResponse, SwipeAction } from '@aventi/contracts';
import { RANKING_CONSTANTS } from '@aventi/contracts';
import { EventCard } from '../components/EventCard';
import { EventDetailModal } from '../components/EventDetailModal';
import { FeedActionRail } from '../components/FeedActionRail';
import { GlassPanel } from '../components/GlassPanel';
import { LoadingConstruct } from '../components/LoadingConstruct';
import { Ionicons } from '@expo/vector-icons';

import { aventiApi } from '../lib/api';
import { useAuthSession } from '../lib/auth-session';
import { useLocationGate } from '../lib/location-gate';
import { sampleEvents } from '../lib/sample-events';

function buildLocalGuestFeed(
  cursor: string | null,
  limit: number,
  remainingFreePreferenceActions: number,
): FeedResponse {
  const offset = Number.isFinite(Number(cursor)) ? Math.max(0, Number(cursor)) : 0;
  const items = sampleEvents.slice(offset, offset + limit);
  const nextOffset = offset + limit;
  return {
    items,
    nextCursor: nextOffset < sampleEvents.length ? String(nextOffset) : null,
    fallbackStatus: 'none',
    remainingFreePreferenceActions,
    remainingFreeSwipes: remainingFreePreferenceActions,
  };
}

function mergeUniqueEvents(existing: EventCardModel[], incoming: EventCardModel[]): EventCardModel[] {
  if (existing.length === 0) return incoming;
  const seen = new Set(existing.map((event) => event.id));
  const appended = incoming.filter((event) => !seen.has(event.id));
  return appended.length > 0 ? [...existing, ...appended] : existing;
}

export default function HomeScreen() {
  const auth = useAuthSession();
  const location = useLocationGate();
  const queryClient = useQueryClient();
  const { height: windowHeight } = useWindowDimensions();
  const listRef = useRef<FlashListRef<EventCardModel>>(null);
  const impressionSeenRef = useRef<Set<string>>(new Set());
  const viewabilityConfigRef = useRef({ itemVisiblePercentThreshold: 80 });
  const [feedCursor, setFeedCursor] = useState<string | null>(null);
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
  const [filters] = useState({
    date: 'week' as const,
    timeOfDay: undefined as 'morning' | 'afternoon' | 'evening' | 'night' | undefined,
    price: 'any' as const,
    radiusMiles: 25,
  });

  const appUnlocked =
    auth.isReady && (auth.isAuthenticated || auth.hasEnteredGuestMode || !auth.isSupabaseConfigured);
  const localGuestFallback = auth.isLocalGuestMode;
  const serverCallsEnabled =
    appUnlocked && !localGuestFallback && (auth.isAuthenticated || !auth.isSupabaseConfigured);
  const canPersistServerActions =
    !localGuestFallback && (auth.isAuthenticated || !auth.isSupabaseConfigured);

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
      auth.session?.user.id ?? (localGuestFallback ? 'local-guest' : 'no-session'),
      location.effectiveLocation?.latitude,
      location.effectiveLocation?.longitude,
      filters.date,
      filters.timeOfDay,
      filters.price,
      filters.radiusMiles,
      feedCursor,
      localGuestFallback ? 'local' : 'server',
    ],
    enabled: appUnlocked && Boolean(location.deviceLocation && location.effectiveLocation),
    queryFn: () => {
      if (localGuestFallback) {
        return Promise.resolve(buildLocalGuestFeed(feedCursor, 20, remainingPreferenceActions));
      }
      return aventiApi.getFeed({
        latitude: location.effectiveLocation!.latitude,
        longitude: location.effectiveLocation!.longitude,
        limit: 20,
        filters,
        cursor: feedCursor ?? undefined,
      });
    },
    staleTime: localGuestFallback ? 0 : 15_000,
  });

  useEffect(() => {
    if (!appUnlocked || location.status === 'checking') return;
    if (!location.deviceLocation) {
      router.replace('/onboarding/location');
    }
  }, [appUnlocked, location.deviceLocation, location.status]);

  useEffect(() => {
    setFeedCursor(null);
    setNextCursor(null);
    setTimelineEvents([]);
    setEventActions({});
    setActiveEventId(null);
    setDetailVisible(false);
    setDetailEvent(null);
    impressionSeenRef.current.clear();
    listRef.current?.scrollToOffset({ offset: 0, animated: false });
  }, [
    auth.session?.user.id,
    localGuestFallback,
    location.effectiveLocation?.latitude,
    location.effectiveLocation?.longitude,
    location.isTravelModeActive,
  ]);

  useEffect(() => {
    if (!feedQuery.data) return;
    const remaining =
      feedQuery.data.remainingFreePreferenceActions ?? feedQuery.data.remainingFreeSwipes;
    if (typeof remaining === 'number') {
      setRemainingPreferenceActions(remaining);
    }
    setNextCursor(feedQuery.data.nextCursor ?? null);
    setTimelineEvents((previous) =>
      feedCursor === null ? feedQuery.data.items : mergeUniqueEvents(previous, feedQuery.data.items),
    );
  }, [feedCursor, feedQuery.data]);

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

  const favoriteMutation = useMutation({
    mutationFn: (eventId: string) => aventiApi.saveFavorite(eventId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['favorites'] });
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
    if (location.status === 'checking' && !location.deviceLocation) return 'Checking Location';
    if (!location.deviceLocation) return 'Location Required';
    if (feedQuery.isLoading && timelineEvents.length === 0) return 'Synthesizing Feed';
    if (feedQuery.isError && timelineEvents.length === 0) return 'Feed Unavailable';
    if (timelineEvents.length === 0) return 'No Events In Feed';
    return 'Tonight in Motion';
  }, [
    appUnlocked,
    feedQuery.isError,
    feedQuery.isLoading,
    location.deviceLocation,
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
          setUiNotice('Saved only for this local session. Start guest auth or sign in to persist Favorites.');
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
    if (!appUnlocked || !location.deviceLocation) return;
    if (feedQuery.isFetching) return;
    if (!nextCursor) return;
    if (feedCursor === nextCursor) return;
    setFeedCursor(nextCursor);
  }, [appUnlocked, feedCursor, feedQuery.isFetching, location.deviceLocation, nextCursor]);

  const handleRefreshFeed = () => {
    setNextCursor(null);
    setTimelineEvents([]);
    setEventActions({});
    setActiveEventId(null);
    impressionSeenRef.current.clear();
    listRef.current?.scrollToOffset({ offset: 0, animated: true });
    if (feedCursor === null) {
      void feedQuery.refetch();
      return;
    }
    setFeedCursor(null);
  };

  const handleOpenProfile = () => {
    router.push('/profile');
  };

  const handleOpenFavorites = () => {
    if (!auth.requireSessionBackedGuestOrAccount('favorites')) {
      setUiNotice('Start a guest session or sign in to open Favorites.');
      return;
    }
    router.push('/favorites');
  };

  const statusLine = !appUnlocked
    ? 'Choose guest mode or sign in to begin discovery'
    : !location.deviceLocation
      ? 'Complete the location step to initialize your local feed'
      : location.errorMessage
        ? location.errorMessage
        : feedQuery.isLoading && timelineEvents.length === 0
          ? 'Synthesizing your local event feed...'
          : feedQuery.isError && timelineEvents.length === 0
            ? localGuestFallback
              ? 'Local guest fallback is active and server sync is unavailable.'
              : 'Could not load the feed from FastAPI. Check EXPO_PUBLIC_API_BASE_URL and backend status.'
            : `${remainingPreferenceActions} free preference actions left today • ${location.effectiveLocation?.label ?? 'Local Mode'}`;

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

            <View className="absolute left-3 top-3 rounded-full border border-white/10 bg-black/45 px-3 py-1">
              <Text className="text-[10px] uppercase tracking-[1.2px] text-white/80">
                {activeEventId === item.id ? 'Now Showing' : 'Up Next'}
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
      activeEventId,
      eventActions,
      handleEventAction,
      handleShareEvent,
      isPremium,
      pageHeight,
      remainingPreferenceActions,
    ],
  );

  const listFooter = useMemo(() => {
    if (feedQuery.isFetching && timelineEvents.length > 0) {
      return (
        <View className="pb-6 pt-2">
          <Text className="text-center text-[11px] uppercase tracking-[1.4px] text-white/55">
            Loading more events...
          </Text>
        </View>
      );
    }
    if (!nextCursor && timelineEvents.length > 0) {
      return (
        <View className="pb-6 pt-2">
          <Text className="text-center text-[11px] uppercase tracking-[1.4px] text-white/40">
            End of current feed
          </Text>
        </View>
      );
    }
    return null;
  }, [feedQuery.isFetching, nextCursor, timelineEvents.length]);

  return (
    <View className="flex-1 bg-black px-4 pt-14">
      <View className="mb-2 flex-row items-center justify-between">
        <View>
          <Text className="text-xs uppercase tracking-[3px] text-white/55">Aventi</Text>
          <Text className="mt-2 text-2xl font-bold uppercase tracking-[2px] text-white">
            {headerLabel}
          </Text>
        </View>
        <View className="flex-row gap-3">
          <Pressable
            onPress={handleOpenFavorites}
            className="h-10 w-10 items-center justify-center rounded-full bg-white/10 active:scale-95"
          >
            <Ionicons name="heart-outline" size={24} color="white" />
          </Pressable>
          <Pressable
            onPress={handleOpenProfile}
            className="h-10 w-10 items-center justify-center rounded-full bg-white/10 active:scale-95"
          >
            <Ionicons name="person-outline" size={22} color="white" />
          </Pressable>
        </View>
      </View>

      <View className="mb-4 flex-row flex-wrap gap-2">
        {[
          filters.date === 'week' ? 'This Week' : filters.date,
          filters.timeOfDay ?? 'All Times',
          `Within ${filters.radiusMiles} mi`,
          location.isTravelModeActive ? 'Travel Mode' : 'Local Mode',
          isPremium ? '21+' : '21+ (Premium)',
        ].map((chip) => (
          <Pressable
            key={chip}
            onPress={() => {
              if (chip.includes('Premium') && !isPremium) {
                auth.openAuthPrompt('premium');
              }
            }}
            className="rounded-full border border-white/10 bg-white/5 px-3 py-2 active:scale-95"
          >
            <Text className="text-[11px] uppercase tracking-[1.2px] text-white/75">{chip}</Text>
          </Pressable>
        ))}
      </View>

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
          <LoadingConstruct label="Choose guest mode or sign in to initialize Aventi" />
        ) : location.status === 'checking' && !location.deviceLocation ? (
          <LoadingConstruct label="Checking location access before loading Aventi" />
        ) : !location.deviceLocation ? (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">Location Setup</Text>
            <Text className="mt-2 text-lg font-semibold text-white">Finish onboarding to unlock your local feed.</Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              Grant device location, retry after changing Settings, and optionally choose a Travel Mode override.
            </Text>
            <Pressable
              onPress={handleOpenProfile}
              className="mt-4 self-start rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                Open Profile to configure
              </Text>
            </Pressable>
          </GlassPanel>
        ) : feedQuery.isLoading && timelineEvents.length === 0 ? (
          <LoadingConstruct
            label={
              localGuestFallback
                ? 'Loading local guest feed'
                : `Synthesizing your ${location.effectiveLocation?.city ?? 'city'} feed from Aventi API`
            }
          />
        ) : feedQuery.isError && timelineEvents.length === 0 ? (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">Feed Error</Text>
            <Text className="mt-2 text-lg font-semibold text-white">
              {localGuestFallback ? 'Local guest feed fallback is unavailable.' : 'FastAPI feed is unavailable.'}
            </Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              {localGuestFallback
                ? 'Reopen auth and choose guest again to retry anonymous sign-in, or sign in with an account.'
                : 'Start the backend (`pnpm backend:dev`) and ensure `EXPO_PUBLIC_API_BASE_URL` points to it.'}
            </Text>
            {localGuestFallback ? (
              <Pressable
                onPress={() => auth.openAuthPrompt('sync')}
                className="mt-4 self-start rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Open Auth</Text>
              </Pressable>
            ) : null}
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
            onViewableItemsChanged={onViewableItemsChanged}
            viewabilityConfig={viewabilityConfigRef.current}
            ListFooterComponent={listFooter}
          />
        ) : (
          <GlassPanel>
            <Text className="text-sm uppercase tracking-[2px] text-white/65">Feed Complete</Text>
            <Text className="mt-2 text-lg font-semibold text-white">
              You reached the end of the current event stream.
            </Text>
            <Text className="mt-2 text-sm leading-5 text-white/70">
              Aventi auto-loads more events as you scroll. You can also refresh to start from the top.
            </Text>
            <View className="mt-4 flex-row gap-3">
              {nextCursor ? (
                <Pressable
                  onPress={handleLoadMore}
                  className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
                >
                  <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                    Load More
                  </Text>
                </Pressable>
              ) : null}
              <Pressable
                onPress={handleRefreshFeed}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  Refresh Feed
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
    </View>
  );
}
