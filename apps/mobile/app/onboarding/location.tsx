import type { Destination } from '@aventi/contracts';
import { router } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, Text, View } from 'react-native';
import { GlassPanel } from '../../components/GlassPanel';
import { LoadingConstruct } from '../../components/LoadingConstruct';
import { TravelDestinationPicker } from '../../components/TravelDestinationPicker';
import { useLocationGate } from '../../lib/location-gate';

function statusHeading(status: ReturnType<typeof useLocationGate>['status']) {
  switch (status) {
    case 'checking':
      return 'Checking Location Access';
    case 'needs-permission':
      return 'Enable Location';
    case 'denied':
    case 'error':
      return 'Choose Your Location';
    case 'ready':
      return 'Location Ready';
  }
}

export default function LocationOnboardingScreen() {
  const location = useLocationGate();
  const [travelError, setTravelError] = useState<string | null>(null);
  const activeLocation = location.effectiveLocation;
  const heading = activeLocation ? 'Location Ready' : statusHeading(location.status);

  const handleSelectDestination = async (destination: Destination) => {
    setTravelError(null);
    try {
      await location.setTravelModeOverride(destination);
    } catch (error) {
      setTravelError(error instanceof Error ? error.message : 'Could not enable Travel Mode right now.');
    }
  };

  const handleClearTravelDestination = async () => {
    setTravelError(null);
    try {
      await location.setTravelModeOverride(null);
    } catch (error) {
      setTravelError(error instanceof Error ? error.message : 'Could not clear Travel Mode right now.');
    }
  };

  return (
    <ScrollView
      className="flex-1 bg-black px-4 pt-14"
      contentContainerStyle={{ paddingBottom: 24 }}
      keyboardShouldPersistTaps="handled"
    >
      <Text className="text-xs uppercase tracking-[3px] text-white/55">Aventi</Text>
      <Text className="mt-2 text-3xl font-bold uppercase tracking-[2px] text-white">{heading}</Text>
      <Text className="mt-3 text-sm leading-5 text-white/70">
        Use device location for nearby discovery, or choose a supported US destination with Travel Mode.
      </Text>

      <GlassPanel className="mt-5">
        {location.status === 'checking' && !activeLocation ? (
          <LoadingConstruct label="Checking location access…" />
        ) : (
          <View className="gap-3">
            <View>
              <Text className="text-xs uppercase tracking-[1.8px] text-white/60">Status</Text>
              <Text className="mt-1 text-base font-semibold text-white">
                {activeLocation
                  ? activeLocation.source === 'travel'
                    ? `${location.travelModeOverride?.label ?? 'Travel destination'} is active`
                    : `Device location ready${location.deviceLocation?.city ? ` (${location.deviceLocation.city})` : ''}`
                  : location.status === 'denied'
                    ? 'Device location permission denied'
                    : location.status === 'needs-permission'
                      ? 'Device location is not enabled'
                      : location.status === 'error'
                        ? 'Device location is unavailable'
                        : 'Checking…'}
              </Text>
              {location.errorMessage && !activeLocation ? (
                <Text className="mt-2 text-sm leading-5 text-white/70">{location.errorMessage}</Text>
              ) : null}
              {location.profileSyncError ? (
                <Text className="mt-2 text-xs uppercase tracking-[1px] text-amber-200/80">
                  Profile sync warning: {location.profileSyncError}
                </Text>
              ) : null}
            </View>

            <View className="flex-row flex-wrap gap-3">
              <Pressable
                onPress={() => void location.requestDeviceLocation()}
                className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                  {location.deviceLocation ? 'Refresh Device Location' : 'Enable Device Location'}
                </Text>
              </Pressable>

              <Pressable
                onPress={() => void location.recheckPermissionAndLocation()}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">Re-check</Text>
              </Pressable>

              {(location.status === 'denied' || location.status === 'error') && !location.deviceLocation ? (
                <Pressable
                  onPress={() => void Linking.openSettings()}
                  className="rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
                >
                  <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                    Open Settings
                  </Text>
                </Pressable>
              ) : null}
            </View>

            {activeLocation ? (
              <Pressable
                onPress={() => router.replace('/' as never)}
                className="mt-1 rounded-full border border-white/15 bg-white px-4 py-3 active:scale-95"
              >
                <Text className="text-center text-xs font-semibold uppercase tracking-[1.6px] text-black">
                  Continue To Feed
                </Text>
              </Pressable>
            ) : null}
          </View>
        )}
      </GlassPanel>

      <GlassPanel className="mt-5">
        <Text className="text-xs uppercase tracking-[1.8px] text-white/60">Travel Mode</Text>
        <Text className="mt-2 text-sm leading-5 text-white/70">
          Unlimited members can search Aventi&apos;s supported US destinations. Your selection is saved only for this account and works without device location access.
        </Text>

        {location.canUseTravelMode ? (
          <View className="mt-4">
            <TravelDestinationPicker
              selectedDestination={location.travelModeOverride}
              onSelect={handleSelectDestination}
            />
            {travelError ? <Text className="mt-3 text-sm leading-5 text-rose-200/85">{travelError}</Text> : null}
            {location.travelModeOverride ? (
              <View className="mt-4 rounded-2xl border border-[#A67CFF]/40 bg-[#A67CFF]/10 px-4 py-3">
                <Text className="text-xs uppercase tracking-[1.4px] text-[#D8C7FF]">Travel Mode Active</Text>
                <Text className="mt-1 text-base font-semibold text-white">{location.travelModeOverride.label}</Text>
                <Text className="mt-1 text-xs uppercase tracking-[1px] text-white/55">
                  {location.travelModeOverride.city}, {location.travelModeOverride.state} · US
                </Text>
              </View>
            ) : null}
            {location.travelModeOverride ? (
              <Pressable
                onPress={() => void handleClearTravelDestination()}
                className="mt-4 self-start rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  {location.deviceLocation ? 'Use Device Location' : 'Clear Travel Destination'}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : (
          <View className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
            <Text className="text-sm leading-5 text-white/70">
              Upgrade to Aventi Unlimited to search destinations and use Travel Mode.
            </Text>
            <Pressable
              onPress={() => router.push('/(tabs)/profile')}
              className="mt-4 self-start rounded-full bg-white px-4 py-3 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-black">View Plans</Text>
            </Pressable>
          </View>
        )}
      </GlassPanel>
    </ScrollView>
  );
}
