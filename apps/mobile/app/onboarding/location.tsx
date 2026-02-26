import { router } from 'expo-router';
import { Linking, Pressable, ScrollView, Text, View } from 'react-native';
import { GlassPanel } from '../../components/GlassPanel';
import { LoadingConstruct } from '../../components/LoadingConstruct';
import { TRAVEL_MODE_PRESETS, useLocationGate } from '../../lib/location-gate';

function statusHeading(status: ReturnType<typeof useLocationGate>['status']) {
  switch (status) {
    case 'checking':
      return 'Checking Location Access';
    case 'needs-permission':
      return 'Enable Location';
    case 'denied':
      return 'Location Required';
    case 'error':
      return 'Location Unavailable';
    case 'ready':
      return 'Location Ready';
  }
}

export default function LocationOnboardingScreen() {
  const location = useLocationGate();

  const handleContinue = () => {
    router.replace('/' as never);
  };

  const handleOpenSettings = () => {
    void Linking.openSettings();
  };

  return (
    <ScrollView className="flex-1 bg-black px-4 pt-14" contentContainerStyle={{ paddingBottom: 24 }}>
      <Text className="text-xs uppercase tracking-[3px] text-white/55">Aventi</Text>
      <Text className="mt-2 text-3xl font-bold uppercase tracking-[2px] text-white">
        {statusHeading(location.status)}
      </Text>
      <Text className="mt-3 text-sm leading-5 text-white/70">
        Aventi uses your device location to initialize a local discovery feed. Travel Mode is available as an
        override after setup (premium-gated later).
      </Text>

      <GlassPanel className="mt-5">
        {location.status === 'checking' ? (
          <LoadingConstruct label="Checking location access…" />
        ) : (
          <View className="gap-3">
            <View>
              <Text className="text-xs uppercase tracking-[1.8px] text-white/60">Status</Text>
              <Text className="mt-1 text-base font-semibold text-white">
                {location.deviceLocation
                  ? `Device location ready${location.deviceLocation.city ? ` (${location.deviceLocation.city})` : ''}`
                  : location.status === 'denied'
                    ? 'Permission denied'
                    : location.status === 'needs-permission'
                      ? 'Permission not granted yet'
                      : location.status === 'error'
                        ? 'Location services unavailable'
                        : 'Checking…'}
              </Text>
              {location.errorMessage ? (
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
                onPress={() => {
                  void location.requestDeviceLocation();
                }}
                className="rounded-full border border-white/15 bg-white/10 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                  {location.deviceLocation ? 'Refresh Device Location' : 'Enable Location'}
                </Text>
              </Pressable>

              <Pressable
                onPress={() => {
                  void location.recheckPermissionAndLocation();
                }}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  Re-check
                </Text>
              </Pressable>

              {(location.status === 'denied' || location.status === 'error') ? (
                <Pressable
                  onPress={handleOpenSettings}
                  className="rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
                >
                  <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                    Open Settings
                  </Text>
                </Pressable>
              ) : null}
            </View>

            {location.deviceLocation ? (
              <Pressable
                onPress={handleContinue}
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
        <Text className="text-xs uppercase tracking-[1.8px] text-white/60">Travel Mode Preview</Text>
        <Text className="mt-2 text-sm leading-5 text-white/70">
          Browse a destination instead of your current area. This path exists now for testing and will be premium-gated
          later.
        </Text>
        {!location.canUseTravelMode ? (
          <Text className="mt-3 text-sm leading-5 text-white/60">
            Enable device location first to unlock Travel Mode overrides.
          </Text>
        ) : (
          <>
            <View className="mt-4 gap-2">
              {TRAVEL_MODE_PRESETS.map((preset) => {
                const active = location.travelModeOverride?.id === preset.id;
                return (
                  <Pressable
                    key={preset.id}
                    onPress={() => {
                      void location.setTravelModeOverride(preset);
                    }}
                    className={`rounded-2xl border px-4 py-3 active:scale-95 ${
                      active ? 'border-white/30 bg-white/15' : 'border-white/10 bg-white/5'
                    }`}
                  >
                    <Text className="text-xs uppercase tracking-[1.4px] text-white/60">
                      {active ? 'Travel Mode Active' : 'Travel Preset'}
                    </Text>
                    <Text className="mt-1 text-base font-semibold text-white">{preset.label}</Text>
                    <Text className="mt-1 text-xs uppercase tracking-[1px] text-white/55">
                      {preset.city} • {preset.timezone}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <View className="mt-4 flex-row flex-wrap gap-3">
              <Pressable
                onPress={() => {
                  void location.setTravelModeOverride(null);
                }}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-3 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  Use Current Location
                </Text>
              </Pressable>
              {location.deviceLocation ? (
                <Text className="self-center text-xs uppercase tracking-[1.1px] text-white/55">
                  Device: {location.deviceLocation.city ?? 'Current Location'}
                </Text>
              ) : null}
            </View>
          </>
        )}
      </GlassPanel>
    </ScrollView>
  );
}
