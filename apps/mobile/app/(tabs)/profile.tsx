import { router } from 'expo-router';
import { Alert, Linking, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RANKING_CONSTANTS } from '@aventi/contracts';

import { MembershipPlans } from '../../components/MembershipPlans';
import { GlassPanel } from '../../components/GlassPanel';
import { aventiApi } from '../../lib/api';
import { useAuthSession } from '../../lib/auth-session';
import { useLocationGate } from '../../lib/location-gate';
import {
  getMembershipManagementUrl,
  isRevenueCatConfigured,
  loadMembershipOffering,
  purchaseMembership,
  restoreMembership,
  type MembershipOffer,
} from '../../lib/revenuecat';
import { pendingSwipeQueue } from '../../lib/swipe-queue';

export default function ProfileScreen() {
  const auth = useAuthSession();
  const location = useLocationGate();
  const queryClient = useQueryClient();

  const appUnlocked = auth.isReady && auth.isAuthenticated;
  const serverCallsEnabled = appUnlocked;

  const bootstrapQuery = useQuery({
    queryKey: ['me', 'bootstrap', auth.session?.user.id ?? 'no-session'],
    enabled: serverCallsEnabled,
    queryFn: () => aventiApi.bootstrapMe(),
    staleTime: 60_000,
  });

  const entitlementsQuery = useQuery({
    queryKey: ['membership', 'entitlements', auth.session?.user.id ?? 'no-session'],
    enabled: auth.isFullAccount,
    queryFn: () => aventiApi.getEntitlements(),
  });

  const offeringQuery = useQuery({
    queryKey: ['membership', 'offering', auth.session?.user.id ?? 'no-session'],
    enabled: auth.isFullAccount && isRevenueCatConfigured() && entitlementsQuery.data?.purchasesEnabled === true,
    queryFn: () => loadMembershipOffering(auth.session!.user.id),
  });

  const deletionQuery = useQuery({
    queryKey: ['me', 'deletion', auth.session?.user.id ?? 'no-session'],
    enabled: auth.isFullAccount,
    queryFn: () => aventiApi.getAccountDeletionStatus(),
    refetchInterval: (query) => ['pending', 'processing'].includes(query.state.data?.status ?? '') ? 5_000 : false,
  });

  const purchaseMutation = useMutation({
    mutationFn: (offer: MembershipOffer) => purchaseMembership(auth.session!.user.id, offer),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['membership'] }),
  });

  const restoreMutation = useMutation({
    mutationFn: () => restoreMembership(auth.session!.user.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['membership'] }),
  });

  const deletionMutation = useMutation({
    mutationFn: () => aventiApi.requestAccountDeletion(),
    onSuccess: async (status) => {
      const userId = auth.session!.user.id;
      await pendingSwipeQueue.clearAccount(userId);
      queryClient.setQueryData(['me', 'deletion', userId], status);
      if (status.status === 'completed') {
        queryClient.removeQueries({ queryKey: ['event-insights'] });
        queryClient.removeQueries({ queryKey: ['favorites'] });
        queryClient.removeQueries({ queryKey: ['membership'] });
        await auth.signOut();
      }
    },
  });

  const feedQuery = useQuery<{
    remainingFreePreferenceActions?: number;
    remainingFreeSwipes?: number;
  }>({
    queryKey: [
      'feed',
      auth.session?.user.id ?? 'no-session',
      location.effectiveLocation?.latitude,
      location.effectiveLocation?.longitude,
      'week',
      undefined,
      'any',
      10,
      null,
      'server',
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
      : 'Not Signed In';

  const authModeDescription = auth.isFullAccount
    ? auth.email ?? 'Signed in'
    : auth.isAnonymousUser
      ? 'Temporary Supabase guest session active. Upgrade later without losing this profile.'
      : auth.guestAuthError ?? 'Start a guest session or sign in to continue.';

  const authActionLabel = auth.isFullAccount ? 'Sign Out' : auth.isAnonymousUser ? 'Upgrade' : 'Sign In';

  const statusLine = !appUnlocked
    ? 'Choose guest mode or sign in to begin discovery'
    : !location.effectiveLocation
      ? location.errorMessage ?? 'Choose device location or a travel destination to initialize your local feed'
      : `${remainingActions} free preference actions left today • ${location.effectiveLocation.label}`;

  const handleAuthAction = async () => {
    if (auth.isFullAccount) {
      try {
        await auth.signOut();
        queryClient.removeQueries({ queryKey: ['event-insights'] });
        queryClient.removeQueries({ queryKey: ['favorites'] });
        queryClient.removeQueries({ queryKey: ['membership'] });
        queryClient.removeQueries({ queryKey: ['me'] });
      } catch (error) {
        Alert.alert('Sign out failed', error instanceof Error ? error.message : 'Please try again.');
      }
      return;
    }
    auth.openAuthPrompt(auth.isAnonymousUser ? 'sync' : 'welcome');
  };

  const handleOpenLocationSetup = () => {
    router.push('/onboarding/location');
  };

  const handlePremiumPurchase = () => {
    if (!auth.requireFullAccount('premium-purchase')) return;
    void offeringQuery.refetch();
  };

  const handlePremiumRestore = () => {
    if (!auth.requireFullAccount('premium-restore')) return;
    restoreMutation.mutate();
  };

  const handleManageSubscription = async () => {
    if (!auth.requireFullAccount('premium')) return;
    try {
      const url = await getMembershipManagementUrl(auth.session!.user.id);
      if (!url) throw new Error('No active subscription management link was returned.');
      await Linking.openURL(url);
    } catch (error) {
      Alert.alert('Manage subscription', error instanceof Error ? error.message : 'Could not open subscription management.');
    }
  };

  const handleDeleteAccount = () => {
    Alert.alert('Delete Aventi account?', 'This deletes your profile, favorites, and membership link. Store subscriptions continue until cancelled separately through Manage subscription.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete account', style: 'destructive', onPress: () => deletionMutation.mutate() },
    ]);
  };

  return (
    <View className="flex-1 px-4 pt-14 bg-black">
      {/* Header */}
      <View className="flex-row justify-between items-center mb-6">
        <Pressable
          onPress={() => router.back()}
          className="justify-center items-center w-10 h-10 rounded-full bg-white/10 active:scale-95"
        >
          <Ionicons name="chevron-back" size={24} color="white" />
        </Pressable>
        <Text className="text-sm font-semibold uppercase tracking-[2px] text-white">Profile & Settings</Text>
        <View className="w-10" />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Identity Mode Panel */}
        <GlassPanel className="mb-4">
          <View className="flex-row gap-4 justify-between items-start">
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
                onPress={() => void handleAuthAction()}
                className="px-4 py-3 rounded-full border border-white/15 bg-white/10 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                  {authActionLabel}
                </Text>
              </Pressable>
            </View>
          </View>
          <MembershipPlans offers={offeringQuery.data?.offers ?? []} enabled={entitlementsQuery.data?.purchasesEnabled === true} loading={entitlementsQuery.isLoading} busy={purchaseMutation.isPending || restoreMutation.isPending} onPurchase={offer => purchaseMutation.mutate(offer)} onLoad={handlePremiumPurchase} onRestore={handlePremiumRestore} onManage={() => void handleManageSubscription()} />
          {entitlementsQuery.data ? <Text className="mt-3 text-xs text-white/60">{entitlementsQuery.data.isPremium ? 'Unlimited is active.' : 'Free plan active.'}</Text> : null}
          {purchaseMutation.isPending || restoreMutation.isPending ? <Text className="mt-2 text-xs text-white/55">Confirming with your store…</Text> : null}
          {offeringQuery.isError || purchaseMutation.isError || restoreMutation.isError ? <Text className="mt-2 text-xs text-rose-300">{(purchaseMutation.error ?? restoreMutation.error ?? offeringQuery.error)?.message ?? 'Membership request failed.'}</Text> : null}
          {!isRevenueCatConfigured() ? <Text className="mt-2 text-xs text-amber-200/80">Purchases are unavailable in this build.</Text> : null}
        </GlassPanel>

        {auth.isFullAccount ? (
          <GlassPanel className="mb-4">
            <Text className="text-xs uppercase tracking-[2px] text-white/60">Account deletion</Text>
            <Text className="mt-2 text-sm leading-5 text-white/65">Status: {deletionQuery.data?.status ?? 'not requested'}</Text>
            {deletionMutation.isError ? <Text className="mt-2 text-xs text-rose-300">{deletionMutation.error.message}</Text> : null}
            <Pressable disabled={deletionMutation.isPending || ['pending', 'processing', 'completed'].includes(deletionQuery.data?.status ?? '')} onPress={handleDeleteAccount} className="mt-4 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-3 disabled:opacity-40">
              <Text className="text-center text-xs font-semibold uppercase tracking-[1.4px] text-rose-200">{deletionMutation.isPending ? 'Scheduling deletion…' : 'Delete account'}</Text>
            </Pressable>
          </GlassPanel>
        ) : null}

        {/* Discovery Status Panel */}
        <GlassPanel className="mb-4">
          <View className="flex-row gap-4 justify-between items-center">
            <View className="flex-1">
              <Text className="text-xs uppercase tracking-[2px] text-white/60">Discovery Status</Text>
              <Text className="mt-1 text-base font-semibold text-white">{statusLine}</Text>
              {bootstrapQuery.isError && serverCallsEnabled ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-rose-300/80">
                  Bootstrap request failed (dev auth bypass may still allow feed calls)
                </Text>
              ) : null}
              {location.effectiveLocation ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-white/55">
                  Active coordinates: {location.effectiveLocation.latitude.toFixed(4)},{' '}
                  {location.effectiveLocation.longitude.toFixed(4)}
                </Text>
              ) : null}
              {location.isTravelModeActive ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-sky-200/80">
                  Travel Mode is active. These coordinates are being used for discovery right now.
                </Text>
              ) : null}
              {location.profileSyncError ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-amber-200/80">
                  Profile location sync warning: {location.profileSyncError}
                </Text>
              ) : null}
              {!auth.isAuthenticated && auth.guestAuthError ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-amber-200/85">
                  Guest auth retry needed: {auth.guestAuthError}
                </Text>
              ) : null}
            </View>
            <Pressable
              onPress={handleOpenLocationSetup}
              className="px-4 py-3 rounded-full border border-white/15 bg-white/10 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                Location & Travel
              </Text>
            </Pressable>
          </View>
        </GlassPanel>
      </ScrollView>
    </View>
  );
}
