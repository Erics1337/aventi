import { useEffect, useMemo, useState } from 'react';
import { router } from 'expo-router';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { EventCard as EventCardModel, FavoritesResponse } from '@aventi/contracts';
import { EventDetailModal } from '../components/EventDetailModal';
import { GlassPanel } from '../components/GlassPanel';
import { LoadingConstruct } from '../components/LoadingConstruct';
import { aventiApi } from '../lib/api';
import { useAuthSession } from '../lib/auth-session';

function formatEventTime(event: EventCardModel) {
  return new Date(event.startsAt).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

interface FavoriteEventRowProps {
  event: EventCardModel;
  isRemoving: boolean;
  onOpen: (event: EventCardModel) => void;
  onRemove: (eventId: string) => void;
}

function FavoriteEventRow({ event, isRemoving, onOpen, onRemove }: FavoriteEventRowProps) {
  return (
    <GlassPanel className="mb-3">
      <View className="flex-row items-start justify-between gap-4">
        <View className="flex-1">
          <Text className="text-[11px] uppercase tracking-[1.8px] text-white/55">{event.category}</Text>
          <Text className="mt-1 text-base font-semibold text-white" numberOfLines={2}>
            {event.title}
          </Text>
          <Text className="mt-1 text-sm text-white/75" numberOfLines={1}>
            {event.venueName}
            {event.city ? ` - ${event.city}` : ''}
          </Text>
          <Text className="mt-1 text-xs text-white/60">{formatEventTime(event)}</Text>
          <View className="mt-3 flex-row flex-wrap gap-2">
            {event.vibes.slice(0, 4).map((vibe) => (
              <View key={vibe} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
                <Text className="text-[10px] uppercase tracking-[1px] text-white/75">{vibe}</Text>
              </View>
            ))}
          </View>
        </View>
        <View className="w-[112px] gap-2">
          <Pressable
            onPress={() => onOpen(event)}
            className="rounded-xl border border-white/15 bg-white/10 px-3 py-3 active:scale-95"
          >
            <Text className="text-center text-[11px] font-semibold uppercase tracking-[1.2px] text-white">
              View
            </Text>
          </Pressable>
          <Pressable
            disabled={isRemoving}
            onPress={() => onRemove(event.id)}
            className={`rounded-xl border px-3 py-3 ${
              isRemoving ? 'border-white/5 bg-white/5' : 'border-rose-300/20 bg-rose-400/10 active:scale-95'
            }`}
          >
            <Text
              className={`text-center text-[11px] font-semibold uppercase tracking-[1.2px] ${
                isRemoving ? 'text-white/40' : 'text-rose-100/90'
              }`}
            >
              {isRemoving ? 'Removing...' : 'Remove'}
            </Text>
          </Pressable>
        </View>
      </View>
    </GlassPanel>
  );
}

interface MissingFavoriteRowProps {
  eventId: string;
  isRemoving: boolean;
  onRemove: (eventId: string) => void;
}

function MissingFavoriteRow({ eventId, isRemoving, onRemove }: MissingFavoriteRowProps) {
  return (
    <View className="mb-2 flex-row items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <View className="flex-1">
        <Text className="text-xs uppercase tracking-[1.2px] text-white/50">Unavailable Event</Text>
        <Text className="mt-1 text-xs text-white/70" numberOfLines={1}>
          {eventId}
        </Text>
      </View>
      <Pressable
        disabled={isRemoving}
        onPress={() => onRemove(eventId)}
        className={`rounded-full border px-3 py-2 ${
          isRemoving ? 'border-white/5 bg-white/5' : 'border-white/10 bg-white/10 active:scale-95'
        }`}
      >
        <Text className={`text-[10px] font-semibold uppercase tracking-[1px] ${isRemoving ? 'text-white/40' : 'text-white/85'}`}>
          {isRemoving ? 'Removing...' : 'Clear'}
        </Text>
      </Pressable>
    </View>
  );
}

export default function FavoritesScreen() {
  const auth = useAuthSession();
  const queryClient = useQueryClient();
  const [uiNotice, setUiNotice] = useState<string | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<EventCardModel | null>(null);
  const favoritesQueryKey = ['favorites', auth.session?.user.id ?? 'no-session'] as const;

  useEffect(() => {
    if (!uiNotice) return;
    const timer = setTimeout(() => setUiNotice(null), 3200);
    return () => clearTimeout(timer);
  }, [uiNotice]);

  const favoritesQuery = useQuery({
    queryKey: favoritesQueryKey,
    enabled: auth.isReady && auth.isAuthenticated,
    queryFn: () => aventiApi.getFavorites(),
    staleTime: 20_000,
  });

  const removeFavoriteMutation = useMutation({
    mutationFn: (eventId: string) => aventiApi.deleteFavorite(eventId),
    onMutate: async (eventId) => {
      await queryClient.cancelQueries({ queryKey: favoritesQueryKey });
      const previous = queryClient.getQueryData<FavoritesResponse>(favoritesQueryKey);
      queryClient.setQueryData<FavoritesResponse>(favoritesQueryKey, (current) => {
        if (!current) return current;
        return {
          items: current.items.filter((id) => id !== eventId),
          events: current.events?.filter((event) => event.id !== eventId),
        };
      });
      return { previous };
    },
    onError: (_error, _eventId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(favoritesQueryKey, context.previous);
      }
      setUiNotice('Could not remove favorite right now.');
    },
    onSuccess: () => {
      setUiNotice('Removed from Favorites.');
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });

  const favoriteIds = favoritesQuery.data?.items ?? [];
  const favoriteEvents = favoritesQuery.data?.events ?? [];

  const eventById = useMemo(() => new Map(favoriteEvents.map((event) => [event.id, event])), [favoriteEvents]);

  const orderedEvents = useMemo(() => {
    const items: EventCardModel[] = [];
    const seen = new Set<string>();
    for (const id of favoriteIds) {
      const event = eventById.get(id);
      if (event) {
        items.push(event);
        seen.add(id);
      }
    }
    for (const event of favoriteEvents) {
      if (!seen.has(event.id)) {
        items.push(event);
      }
    }
    return items;
  }, [eventById, favoriteEvents, favoriteIds]);

  const unresolvedIds = useMemo(() => favoriteIds.filter((id) => !eventById.has(id)), [eventById, favoriteIds]);

  const handleOpenDetails = (event: EventCardModel) => {
    setSelectedEvent(event);
    setDetailVisible(true);
  };

  const handleRemoveFavorite = (eventId: string) => {
    if (!auth.requireSessionBackedGuestOrAccount('favorites')) {
      setUiNotice('Start a guest session or sign in to manage Favorites.');
      return;
    }
    removeFavoriteMutation.mutate(eventId);
  };

  const identityMode = auth.isFullAccount ? 'Account' : auth.isAnonymousUser ? 'Guest (Anonymous)' : 'Guest (Local)';

  if (!auth.isReady) {
    return (
      <View className="flex-1 bg-black px-4 pt-14">
        <LoadingConstruct label="Preparing your Favorites" />
      </View>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <View className="flex-1 bg-black px-4 pt-14">
        <View className="mb-4 flex-row items-center justify-between">
          <Pressable
            onPress={() => router.back()}
            className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
          >
            <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Back</Text>
          </Pressable>
          <Text className="text-xs uppercase tracking-[3px] text-white/55">Favorites</Text>
        </View>

        <GlassPanel>
          <Text className="text-sm uppercase tracking-[2px] text-white/60">Auth Required</Text>
          <Text className="mt-2 text-lg font-semibold text-white">
            Start a guest session or sign in to use Favorites.
          </Text>
          <Text className="mt-2 text-sm leading-5 text-white/70">
            Local guest mode can swipe, but Favorites persistence needs a Supabase guest session or a full account.
          </Text>
          <View className="mt-4 flex-row gap-3">
            <Pressable
              onPress={() => auth.openAuthPrompt('favorites')}
              className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Open Auth</Text>
            </Pressable>
            <Pressable
              onPress={() => router.replace('/')}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-3 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">Back to Feed</Text>
            </Pressable>
          </View>
        </GlassPanel>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-black px-4 pt-14">
      <View className="mb-4 flex-row items-center justify-between gap-3">
        <Pressable
          onPress={() => router.back()}
          className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
        >
          <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Back</Text>
        </Pressable>
        <View className="flex-1">
          <Text className="text-xs uppercase tracking-[3px] text-white/55">Aventi</Text>
          <Text className="mt-1 text-2xl font-bold uppercase tracking-[2px] text-white">Favorites</Text>
        </View>
        <Pressable
          onPress={() => {
            void favoritesQuery.refetch();
          }}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-3 active:scale-95"
        >
          <Text className="text-xs font-semibold uppercase tracking-[1.2px] text-white/85">Refresh</Text>
        </Pressable>
      </View>

      <GlassPanel className="mb-4">
        <View className="flex-row items-start justify-between gap-4">
          <View className="flex-1">
            <Text className="text-xs uppercase tracking-[2px] text-white/60">Identity Mode</Text>
            <Text className="mt-1 text-base font-semibold text-white">{identityMode}</Text>
            <Text className="mt-1 text-xs leading-5 text-white/65">
              {auth.isAnonymousUser
                ? 'Favorites persist to your anonymous guest profile for this device/session. Upgrade later to keep them across devices.'
                : auth.isFullAccount
                  ? auth.email ?? 'Your full account is active.'
                  : 'Favorites need a Supabase guest session or account.'}
            </Text>
          </View>
          <View className="items-end">
            <Text className="text-[11px] uppercase tracking-[1.5px] text-white/55">Saved</Text>
            <Text className="mt-1 text-xl font-semibold text-white">{favoriteIds.length}</Text>
          </View>
        </View>
        {uiNotice ? <Text className="mt-3 text-xs leading-5 text-emerald-200/90">{uiNotice}</Text> : null}
      </GlassPanel>

      {favoritesQuery.isLoading ? (
        <LoadingConstruct label="Loading your Favorites" />
      ) : favoritesQuery.isError ? (
        <GlassPanel>
          <Text className="text-sm uppercase tracking-[2px] text-white/60">Favorites Error</Text>
          <Text className="mt-2 text-lg font-semibold text-white">Could not load your saved events.</Text>
          <Text className="mt-2 text-sm leading-5 text-white/70">
            Check backend connectivity and auth session state, then retry.
          </Text>
          <Pressable
            onPress={() => {
              void favoritesQuery.refetch();
            }}
            className="mt-4 self-start rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
          >
            <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Retry</Text>
          </Pressable>
        </GlassPanel>
      ) : favoriteIds.length === 0 ? (
        <GlassPanel>
          <Text className="text-sm uppercase tracking-[2px] text-white/60">No Favorites Yet</Text>
          <Text className="mt-2 text-lg font-semibold text-white">
            Swipe right on events in the feed to build your list.
          </Text>
          <Text className="mt-2 text-sm leading-5 text-white/70">
            Your Favorites will show up here, and you can revisit details before booking.
          </Text>
          <Pressable
            onPress={() => router.replace('/')}
            className="mt-4 self-start rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
          >
            <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">Back to Feed</Text>
          </Pressable>
        </GlassPanel>
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} className="flex-1">
          <View className="pb-8">
            {orderedEvents.length > 0 ? (
              <>
                <Text className="mb-2 text-xs uppercase tracking-[2px] text-white/50">Saved Events</Text>
                {orderedEvents.map((event) => (
                  <FavoriteEventRow
                    key={event.id}
                    event={event}
                    isRemoving={removeFavoriteMutation.isPending && removeFavoriteMutation.variables === event.id}
                    onOpen={handleOpenDetails}
                    onRemove={handleRemoveFavorite}
                  />
                ))}
              </>
            ) : null}

            {unresolvedIds.length > 0 ? (
              <GlassPanel className={orderedEvents.length > 0 ? 'mt-2' : undefined}>
                <Text className="text-xs uppercase tracking-[2px] text-white/55">Unavailable Favorites</Text>
                <Text className="mt-2 text-sm leading-5 text-white/70">
                  These saved IDs no longer resolve to an event card. You can clear them from your list.
                </Text>
                <View className="mt-3">
                  {unresolvedIds.map((eventId) => (
                    <MissingFavoriteRow
                      key={eventId}
                      eventId={eventId}
                      isRemoving={removeFavoriteMutation.isPending && removeFavoriteMutation.variables === eventId}
                      onRemove={handleRemoveFavorite}
                    />
                  ))}
                </View>
              </GlassPanel>
            ) : null}
          </View>
        </ScrollView>
      )}

      <EventDetailModal event={selectedEvent} visible={detailVisible} onClose={() => setDetailVisible(false)} />
    </View>
  );
}
