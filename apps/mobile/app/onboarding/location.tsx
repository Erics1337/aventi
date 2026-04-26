import { router } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
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

function parseCoordinateInput(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCoordinateLabel(latitude: number, longitude: number): string {
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
}

export default function LocationOnboardingScreen() {
  const location = useLocationGate();
  const [travelLatitude, setTravelLatitude] = useState('');
  const [travelLongitude, setTravelLongitude] = useState('');
  const [travelLabel, setTravelLabel] = useState('');
  const [travelError, setTravelError] = useState<string | null>(null);

  const parsedTravelLatitude = parseCoordinateInput(travelLatitude);
  const parsedTravelLongitude = parseCoordinateInput(travelLongitude);
  const hasValidLatitude = parsedTravelLatitude !== null && parsedTravelLatitude >= -90 && parsedTravelLatitude <= 90;
  const hasValidLongitude =
    parsedTravelLongitude !== null && parsedTravelLongitude >= -180 && parsedTravelLongitude <= 180;
  const activeLocation = location.effectiveLocation;
  const heading = activeLocation ? 'Location Ready' : statusHeading(location.status);

  const handleContinue = () => {
    router.replace('/' as never);
  };

  const handleOpenSettings = () => {
    void Linking.openSettings();
  };

  const handleApplyTravelCoordinates = async () => {
    if (!hasValidLatitude || !hasValidLongitude) {
      setTravelError('Enter valid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180.');
      return;
    }

    setTravelError(null);

    try {
      await location.setTravelModeCoordinates({
        latitude: parsedTravelLatitude!,
        longitude: parsedTravelLongitude!,
        label: travelLabel.trim() || undefined,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Could not apply these travel coordinates right now.';
      setTravelError(message);
    }
  };

  return (
    <ScrollView className="flex-1 px-4 pt-14 bg-black" contentContainerStyle={{ paddingBottom: 24 }}>
      <Text className="text-xs uppercase tracking-[3px] text-white/55">Aventi</Text>
      <Text className="mt-2 text-3xl font-bold uppercase tracking-[2px] text-white">
        {heading}
      </Text>
      <Text className="mt-3 text-sm leading-5 text-white/70">
        Aventi can use device GPS or a Travel Mode coordinate override to initialize discovery. Travel Mode is
        temporarily open to guests for testing, even though it is planned as a premium feature later.
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
                    ? `Travel Mode ready (${activeLocation.label})`
                    : `Device location ready${location.deviceLocation?.city ? ` (${location.deviceLocation.city})` : ''}`
                  : location.status === 'denied'
                    ? 'Permission denied'
                    : location.status === 'needs-permission'
                      ? 'Permission not granted yet'
                      : location.status === 'error'
                        ? 'Location services unavailable'
                        : 'Checking…'}
              </Text>
              {activeLocation ? (
                <Text className="mt-2 text-sm leading-5 text-white/70">
                  Using {activeLocation.source === 'travel' ? 'Travel Mode' : 'device GPS'} at{' '}
                  {formatCoordinateLabel(activeLocation.latitude, activeLocation.longitude)}.
                </Text>
              ) : null}
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
                onPress={() => {
                  void location.requestDeviceLocation();
                }}
                className="px-4 py-3 rounded-full border border-white/15 bg-white/10 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white">
                  {location.deviceLocation ? 'Refresh Device Location' : 'Enable Location'}
                </Text>
              </Pressable>

              <Pressable
                onPress={() => {
                  void location.recheckPermissionAndLocation();
                }}
                className="px-4 py-3 rounded-full border border-white/15 bg-white/5 active:scale-95"
              >
                <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                  Re-check
                </Text>
              </Pressable>

              {(location.status === 'denied' || location.status === 'error') && !location.deviceLocation ? (
                <Pressable
                  onPress={handleOpenSettings}
                  className="px-4 py-3 rounded-full border border-white/15 bg-white/5 active:scale-95"
                >
                  <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                    Open Settings
                  </Text>
                </Pressable>
              ) : null}
            </View>

            {activeLocation ? (
              <Pressable
                onPress={handleContinue}
                className="px-4 py-3 mt-1 bg-white rounded-full border border-white/15 active:scale-95"
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
          Enter exact coordinates for testing or use a preset destination. These overrides stay on this device and
          drive the feed immediately.
        </Text>
        <View className="p-4 mt-4 rounded-2xl border border-white/10 bg-white/5">
          <Text className="text-xs uppercase tracking-[1.4px] text-white/60">Custom Coordinates</Text>
          <View className="gap-3 mt-3">
            <TextInput
              value={travelLatitude}
              onChangeText={setTravelLatitude}
              placeholder="Latitude"
              placeholderTextColor="rgba(255,255,255,0.35)"
              keyboardType="numbers-and-punctuation"
              autoCapitalize="none"
              autoCorrect={false}
              accessibilityLabel="Latitude"
              accessibilityHint="Enter the latitude coordinate for your location"
              className="px-4 py-3 text-sm text-white rounded-2xl border border-white/10 bg-black/20"
            />
            <TextInput
              value={travelLongitude}
              onChangeText={setTravelLongitude}
              placeholder="Longitude"
              placeholderTextColor="rgba(255,255,255,0.35)"
              keyboardType="numbers-and-punctuation"
              autoCapitalize="none"
              autoCorrect={false}
              accessibilityLabel="Longitude"
              accessibilityHint="Enter the longitude coordinate for your location"
              className="px-4 py-3 text-sm text-white rounded-2xl border border-white/10 bg-black/20"
            />
            <TextInput
              value={travelLabel}
              onChangeText={setTravelLabel}
              placeholder="Optional label (for example, Test Market)"
              placeholderTextColor="rgba(255,255,255,0.35)"
              autoCapitalize="words"
              autoCorrect={false}
              accessibilityLabel="Market label"
              accessibilityHint="Optional name to identify this location"
              className="px-4 py-3 text-sm text-white rounded-2xl border border-white/10 bg-black/20"
            />
            {travelError ? <Text className="text-sm leading-5 text-rose-200/85">{travelError}</Text> : null}
            <Pressable
              onPress={() => {
                void handleApplyTravelCoordinates();
              }}
              className="px-4 py-3 rounded-full border border-white/15 bg-white/10 active:scale-95"
            >
              <Text className="text-center text-xs font-semibold uppercase tracking-[1.5px] text-white">
                Use These Coordinates
              </Text>
            </Pressable>
          </View>
        </View>

        <View className="gap-2 mt-4">
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

        <View className="flex-row flex-wrap gap-3 mt-4">
          {location.deviceLocation ? (
            <Pressable
              onPress={() => {
                void location.setTravelModeOverride(null);
              }}
              className="px-4 py-3 rounded-full border border-white/15 bg-white/5 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                Use Current Location
              </Text>
            </Pressable>
          ) : null}
          {location.travelModeOverride && !location.deviceLocation ? (
            <Pressable
              onPress={() => {
                void location.setTravelModeOverride(null);
              }}
              className="px-4 py-3 rounded-full border border-white/15 bg-white/5 active:scale-95"
            >
              <Text className="text-xs font-semibold uppercase tracking-[1.5px] text-white/85">
                Clear Travel Coordinates
              </Text>
            </Pressable>
          ) : null}
          {activeLocation ? (
            <Text className="self-center text-xs uppercase tracking-[1.1px] text-white/55">
              Active: {activeLocation.label} • {formatCoordinateLabel(activeLocation.latitude, activeLocation.longitude)}
            </Text>
          ) : null}
        </View>
      </GlassPanel>
    </ScrollView>
  );
}
