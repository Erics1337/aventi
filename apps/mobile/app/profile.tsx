import { router } from 'expo-router';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { RANKING_CONSTANTS } from '@aventi/contracts';

import { GlassPanel } from '../components/GlassPanel';
import { aventiApi } from '../lib/api';
import { useAuthSession } from '../lib/auth-session';
import { useLocationGate } from '../lib/location-gate';

export default function ProfileScreen() {
  const auth = useAuthSession();
  const location = useLocationGate();

  const appUnlocked =
    auth.isReady && (auth.isAuthenticated || auth.hasEnteredGuestMode || !auth.isSupabaseConfigured);
  const localGuestFallback = auth.isLocalGuestMode;
  const serverCallsEnabled =
    appUnlocked && !localGuestFallback && (auth.isAuthenticated || !auth.isSupabaseConfigured);

  const bootstrapQuery = useQuery({
    queryKey: ['me', 'bootstrap', auth.session?.user.id ?? 'no-session'],
    enabled: serverCallsEnabled,
    queryFn: () => aventiApi.bootstrapMe(),
    staleTime: 60_000,
  });

  const feedQuery = useQuery<{
    remainingFreePreferenceActions?: number;
    remainingFreeSwipes?: number;
  }>({
    queryKey: [
      'feed',
      auth.session?.user.id ?? (localGuestFallback ? 'local-guest' : 'no-session'),
      location.effectiveLocation?.latitude,
      location.effectiveLocation?.longitude,
      'week',
      undefined,
      'any',
      25,
      null,
      localGuestFallback ? 'local' : 'server',
    ],
    // Only fetching this lightly to get the remaining balance if it's cached.
    // If it's not cached, it won't trigger a full feed fetch just for the balance here.
    enabled: false,
    queryFn: async () => ({}),
  });

  const remainingActions =
    feedQuery.data?.remainingFreePreferenceActions ??
    feedQuery.data?.remainingFreeSwipes ??
    RANKING_CONSTANTS.FREE_PREFERENCE_ACTION_LIMIT_PER_DAY;

  const authModeLabel = auth.isFullAccount
    ? 'Account'
    : auth.isAnonymousUser
      ? 'Guest (Anonymous)'
      : auth.isLocalGuestMode
        ? 'Guest (Local)'
        : 'Not Signed In';

  const authModeDescription = auth.isFullAccount
    ? auth.email ?? 'Signed in'
    : auth.isAnonymousUser
      ? 'Temporary Supabase guest session active. Upgrade later without losing this profile.'
      : auth.isLocalGuestMode
        ? 'Browsing locally without a Supabase guest session. Some data cannot persist.'
        : 'Choose guest mode or sign in to start.';

  const authActionLabel = auth.isFullAccount ? 'Sign Out' : auth.isAnonymousUser ? 'Upgrade' : 'Sign In';

  const statusLine = !appUnlocked
    ? 'Choose guest mode or sign in to begin discovery'
    : !location.deviceLocation
      ? 'Complete the location step to initialize your local feed'
      : location.errorMessage
        ? location.errorMessage
        : `${remainingActions} free preference actions left today • ${location.effectiveLocation?.label ?? 'Local Mode'}`;

  const handleAuthAction = () => {
    if (auth.isFullAccount) {
      void auth.signOut();
      return;
    }
    auth.openAuthPrompt(auth.isAnonymousUser ? 'sync' : 'welcome');
  };

  const handleOpenLocationSetup = () => {
    router.push('/onboarding/location');
  };

  const handlePremiumPurchase = () => {
    if (!auth.requireFullAccount('premium-purchase')) return;
    // Premium purchase flow stub (Stripe is deferred in PRD v1)
  };

  const handlePremiumRestore = () => {
    if (!auth.requireFullAccount('premium-restore')) return;
    // Premium restore flow stub
  };

  return (
    <View className="flex-1 bg-black px-4 pt-14">
      {/* Header */}
      <View className="mb-6 flex-row items-center justify-between">
        <Pressable
          onPress={() => router.back()}
          className="h-10 w-10 items-center justify-center rounded-full bg-white/10 active:scale-95"
        >
          <Ionicons name="chevron-back" size={24} color="white" />
        </Pressable>
        <Text className="text-sm font-semibold uppercase tracking-[2px] text-white">Profile & Settings</Text>
        <View className="w-10" />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Identity Mode Panel */}
        <GlassPanel className="mb-4">
          <View className="flex-row items-start justify-between gap-4">
            <View className="flex-1">
              <Text className="text-xs uppercase tracking-[2px] text-white/60">Identity Mode</Text>
              <Text className="mt-1 text-base font-semibold text-white">{authModeLabel}</Text>
              <Text className="mt-1 text-xs leading-5 text-white/65">{authModeDescription}</Text>
              {!auth.isFullAccount ? (
                <Text className="mt-2 text-[11px] uppercase tracking-[1px] text-white/45">
                  Premium purchase/restore requires a full account. Anonymous guests stay on free tier.
                </Text>
              ) : null}
            </View>
            <View className="gap-2">
              <Pressable
                onPress={handleAuthAction}
                className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                  {authActionLabel}
                </Text>
              </Pressable>
            </View>
          </View>
          <View className="mt-4 flex-row gap-2">
            <Pressable
              onPress={handlePremiumPurchase}
              className="flex-1 rounded-2xl border border-white/20 bg-white/10 px-4 py-3 active:scale-[0.99]"
            >
              <Text className="text-center text-[11px] font-semibold uppercase tracking-[1.2px] text-white">
                Premium Upgrade
              </Text>
            </Pressable>
            <Pressable
              onPress={handlePremiumRestore}
              className="flex-1 rounded-2xl border border-white/15 bg-white/5 px-4 py-3 active:scale-[0.99]"
            >
              <Text className="text-center text-[11px] font-semibold uppercase tracking-[1.2px] text-white/90">
                Restore Premium
              </Text>
            </Pressable>
          </View>
        </GlassPanel>

        {/* Discovery Status Panel */}
        <GlassPanel className="mb-4">
          <View className="flex-row items-center justify-between gap-4">
            <View className="flex-1">
              <Text className="text-xs uppercase tracking-[2px] text-white/60">Discovery Status</Text>
              <Text className="mt-1 text-base font-semibold text-white">{statusLine}</Text>
              {bootstrapQuery.isError && serverCallsEnabled ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-rose-300/80">
                  Bootstrap request failed (dev auth bypass may still allow feed calls)
                </Text>
              ) : null}
              {location.profileSyncError ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-amber-200/80">
                  Profile location sync warning: {location.profileSyncError}
                </Text>
              ) : null}
              {localGuestFallback ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-amber-200/85">
                  Local guest mode: browsing works, but server-backed sync needs Supabase guest auth.
                </Text>
              ) : null}
            </View>
            <Pressable
              onPress={handleOpenLocationSetup}
              className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                Location &amp; Travel
              </Text>
            </Pressable>
          </View>
        </GlassPanel>
      </ScrollView>
    </View>
  );
}
