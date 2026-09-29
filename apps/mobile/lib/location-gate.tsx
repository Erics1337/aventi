import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Location from 'expo-location';
import { AppState, type AppStateStatus } from 'react-native';
import {
  createContext,
  startTransition,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from 'react';
import { aventiApi } from './api';
import { useAuthSession } from './auth-session';
import { useQuery } from '@tanstack/react-query';
import type { Destination } from '@aventi/contracts';

const LEGACY_TRAVEL_MODE_STORAGE_KEY = 'aventi.travel.override.v1';
const TRAVEL_MODE_STORAGE_PREFIX = 'aventi.travel.destination.v2';
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type LocationGateStatus = 'checking' | 'needs-permission' | 'denied' | 'ready' | 'error';

export interface LocationPoint {
  latitude: number;
  longitude: number;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  timezone?: string | null;
}

export type TravelModeOverride = Destination;

interface EffectiveLocation extends LocationPoint {
  source: 'device' | 'travel';
  label: string;
}

interface LocationGateContextValue {
  status: LocationGateStatus;
  deviceLocation: LocationPoint | null;
  effectiveLocation: EffectiveLocation | null;
  travelModeOverride: TravelModeOverride | null;
  canUseTravelMode: boolean;
  isTravelModeActive: boolean;
  errorMessage: string | null;
  profileSyncError: string | null;
  requestDeviceLocation: () => Promise<void>;
  recheckPermissionAndLocation: () => Promise<void>;
  setTravelModeOverride: (override: TravelModeOverride | null) => Promise<void>;
}

const LocationGateContext = createContext<LocationGateContextValue | null>(null);

function travelModeStorageKey(accountId: string): string {
  return `${TRAVEL_MODE_STORAGE_PREFIX}:${accountId}`;
}

function isCanonicalDestination(value: Partial<Destination>): value is Destination {
  return typeof value.id === 'string' && UUID_PATTERN.test(value.id)
    && typeof value.label === 'string' && value.label.length > 0
    && typeof value.city === 'string' && value.city.length > 0
    && typeof value.state === 'string' && value.state.length > 0
    && value.country === 'US'
    && typeof value.latitude === 'number' && Number.isFinite(value.latitude)
    && typeof value.longitude === 'number' && Number.isFinite(value.longitude)
    && (value.timezone === undefined || value.timezone === null || typeof value.timezone === 'string');
}

function resolveLocalTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? null;
  } catch {
    return null;
  }
}

interface GeocodeResult {
  city: string | null;
  state: string | null;
  country: string | null;
}

async function reverseGeocodeLocation(latitude: number, longitude: number): Promise<GeocodeResult> {
  try {
    const results = await Location.reverseGeocodeAsync({ latitude, longitude });
    const first = results[0];
    return {
      city: first?.city ?? first?.district ?? first?.subregion ?? null,
      state: first?.region ?? null,
      country: first?.isoCountryCode ?? first?.country ?? null,
    };
  } catch {
    return { city: null, state: null, country: null };
  }
}

async function buildLocationPoint(latitude: number, longitude: number): Promise<LocationPoint> {
  const [geocode, timezone] = await Promise.all([
    reverseGeocodeLocation(latitude, longitude),
    Promise.resolve(resolveLocalTimezone()),
  ]);
  return {
    latitude,
    longitude,
    city: geocode.city,
    state: geocode.state,
    country: geocode.country,
    timezone,
  };
}

export function LocationGateProvider({ children }: PropsWithChildren) {
  const auth = useAuthSession();
  const accountId = auth.isFullAccount ? auth.session?.user.id ?? null : null;
  const travelEntitlementsQuery = useQuery({
    queryKey: ['membership', 'entitlements', auth.session?.user.id ?? 'no-session'],
    enabled: auth.isFullAccount,
    queryFn: () => aventiApi.getEntitlements(),
    staleTime: 60_000,
  });
  const canUseTravelMode = travelEntitlementsQuery.data?.travelMode === true;
  const travelAccessReady = !auth.isFullAccount || travelEntitlementsQuery.isSuccess || travelEntitlementsQuery.isError;
  const [status, setStatus] = useState<LocationGateStatus>('checking');
  const [deviceLocation, setDeviceLocation] = useState<LocationPoint | null>(null);
  const [travelSelection, setTravelSelection] = useState<{ accountId: string; destination: TravelModeOverride } | null>(null);
  const travelModeOverride = travelSelection?.accountId === accountId ? travelSelection.destination : null;
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [profileSyncError, setProfileSyncError] = useState<string | null>(null);
  const lastSyncedSignature = useRef<string | null>(null);
  const lastMarketSeenSignature = useRef<string | null>(null);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);

  const persistProfileLocation = async (location: LocationPoint) => {
    if (!auth.isReady) {
      return;
    }
    if (!auth.isAuthenticated) {
      setProfileSyncError(null);
      return;
    }
    const timezone = location.timezone ?? resolveLocalTimezone();
    const signature = JSON.stringify({
      accountId: auth.session?.user.id ?? null,
      latitude: Number(location.latitude.toFixed(4)),
      longitude: Number(location.longitude.toFixed(4)),
      city: location.city ?? null,
      state: location.state ?? null,
      country: location.country ?? null,
      timezone,
    });
    if (signature !== lastSyncedSignature.current) {
      try {
        await aventiApi.updateMyLocation({
          latitude: location.latitude,
          longitude: location.longitude,
          city: location.city ?? null,
          state: location.state ?? null,
          country: location.country ?? null,
          timezone,
        });
        lastSyncedSignature.current = signature;
        setProfileSyncError(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to sync profile location.';
        setProfileSyncError(message);
      }
    }

    // Tell the backend this market is currently being used. Bootstraps a new
    // market_inventory_state row + fires an immediate short-term scan on
    // first sighting; otherwise just bumps last_user_active_at. Fire-and-forget:
    // we don't want scan-queue failures to block the UI.
    const marketSeenSignature = JSON.stringify({
      latitude: Number(location.latitude.toFixed(4)),
      longitude: Number(location.longitude.toFixed(4)),
      city: location.city ?? null,
      state: location.state ?? null,
      country: location.country ?? null,
    });
    if (location.city && marketSeenSignature !== lastMarketSeenSignature.current) {
      try {
        await aventiApi.markMarketSeen({
          city: location.city,
          state: location.state ?? null,
          country: location.country ?? null,
          latitude: location.latitude,
          longitude: location.longitude,
        });
        lastMarketSeenSignature.current = marketSeenSignature;
      } catch {
        // Non-fatal: cron will still pick this market up next Monday.
      }
    }
  };

  const applyResolvedLocation = (location: LocationPoint, nextErrorMessage: string | null = null) => {
    startTransition(() => {
      setDeviceLocation(location);
      setStatus('ready');
      setErrorMessage(nextErrorMessage);
    });
    void persistProfileLocation(location);
  };

  const resolveCurrentPosition = async (options?: {
    preferLastKnown?: boolean;
    preserveReadyState?: boolean;
    travelOverrideForEvaluation?: TravelModeOverride | null;
  }) => {
    let seededFromLastKnown = false;
    const fallbackTravelOverride =
      options?.travelOverrideForEvaluation === undefined
        ? travelModeOverride
        : options.travelOverrideForEvaluation;

    if (options?.preferLastKnown && !deviceLocation) {
      try {
        const lastKnown = await Location.getLastKnownPositionAsync();
        if (lastKnown?.coords) {
          const cachedLocation = await buildLocationPoint(lastKnown.coords.latitude, lastKnown.coords.longitude);
          seededFromLastKnown = true;
          applyResolvedLocation(cachedLocation);
        }
      } catch {
        // Ignore missing last-known coordinates and continue to a fresh GPS lookup.
      }
    }

    try {
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const location = await buildLocationPoint(position.coords.latitude, position.coords.longitude);
      applyResolvedLocation(location);
      return;
    } catch {
      if (seededFromLastKnown || (options?.preserveReadyState && deviceLocation)) {
        return;
      }
      if (fallbackTravelOverride) {
        startTransition(() => {
          setStatus('ready');
          setErrorMessage(null);
        });
        return;
      }

      startTransition(() => {
        setStatus('error');
        setErrorMessage('Could not access current GPS coordinates. Check device location services and retry.');
      });
    }
  };

  const checkPermissionAndLocation = async ({
    preserveReadyState = false,
    travelOverrideForEvaluation,
  }: {
    preserveReadyState?: boolean;
    travelOverrideForEvaluation?: TravelModeOverride | null;
  } = {}) => {
    const fallbackTravelOverride =
      travelOverrideForEvaluation === undefined ? travelModeOverride : travelOverrideForEvaluation;
    try {
      if (!preserveReadyState || !deviceLocation) {
        setStatus('checking');
      }
      const permission = await Location.getForegroundPermissionsAsync();

      if (permission.status === 'granted') {
        await resolveCurrentPosition({
          preferLastKnown: !deviceLocation,
          preserveReadyState,
          travelOverrideForEvaluation: fallbackTravelOverride,
        });
        return;
      }

      setDeviceLocation(null);
      if (fallbackTravelOverride) {
        setStatus('ready');
        setErrorMessage(null);
        return;
      }
      setStatus(permission.status === 'denied' ? 'denied' : 'needs-permission');
      if (permission.status === 'denied') {
        setErrorMessage('Location permission is required to initialize your local feed.');
      } else {
        setErrorMessage(null);
      }
    } catch {
      if (fallbackTravelOverride) {
        setStatus('ready');
        setErrorMessage(null);
        return;
      }
      setStatus('error');
      setErrorMessage('Failed to check location permission. Retry in a moment.');
    }
  };

  const recheckPermissionAndLocation = async () => {
    await checkPermissionAndLocation();
  };

  const requestDeviceLocation = async () => {
    try {
      setStatus('checking');
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== 'granted') {
        setDeviceLocation(null);
        if (travelModeOverride) {
          setStatus('ready');
          setErrorMessage(null);
        } else {
          setStatus('denied');
          setErrorMessage('Location permission is required to initialize your local feed.');
        }
        return;
      }
      await resolveCurrentPosition();
    } catch {
      if (travelModeOverride) {
        setStatus('ready');
        setErrorMessage(null);
        return;
      }
      setStatus('error');
      setErrorMessage('Unable to request location permission. Try again.');
    }
  };

  const setTravelModeOverride = async (override: TravelModeOverride | null) => {
    if (override && !canUseTravelMode) {
      throw new Error('Aventi Unlimited is required for Travel Mode.');
    }
    if (override && (!accountId || !isCanonicalDestination(override))) {
      throw new Error('Choose a supported destination from Aventi search.');
    }
    startTransition(() => {
      setTravelSelection(override && accountId ? { accountId, destination: override } : null);
      if (override || !deviceLocation) {
        setErrorMessage(null);
      }
      if (override && !deviceLocation) {
        setStatus('ready');
      }
    });

    try {
      if (override && accountId) {
        await AsyncStorage.setItem(travelModeStorageKey(accountId), JSON.stringify(override));
      } else if (accountId) {
        await AsyncStorage.removeItem(travelModeStorageKey(accountId));
      }
    } catch {
      // Ignore storage failures; override still works for the current session.
    }

    if (!override && !deviceLocation) {
      await checkPermissionAndLocation({ travelOverrideForEvaluation: null });
    }
  };

  useEffect(() => {
    if (!travelAccessReady) return;
    let active = true;

    void (async () => {
      let restoredOverride: TravelModeOverride | null = null;

      try {
        await AsyncStorage.removeItem(LEGACY_TRAVEL_MODE_STORAGE_KEY);
        if (!accountId) {
          setTravelSelection(null);
          await checkPermissionAndLocation({ travelOverrideForEvaluation: null });
          return;
        }
        const scopedKey = travelModeStorageKey(accountId);
        const stored = await AsyncStorage.getItem(scopedKey);
        if (!active) {
          return;
        }
        if (!stored) {
          setTravelSelection(null);
          await checkPermissionAndLocation({ travelOverrideForEvaluation: null });
          return;
        }
        if (travelEntitlementsQuery.isError) {
          setTravelSelection(null);
          await checkPermissionAndLocation({ travelOverrideForEvaluation: null });
          return;
        }
        if (!canUseTravelMode) {
          await AsyncStorage.removeItem(scopedKey);
          setTravelSelection(null);
          await checkPermissionAndLocation({ travelOverrideForEvaluation: null });
          return;
        }
        const parsed = JSON.parse(stored) as Partial<TravelModeOverride>;
        if (isCanonicalDestination(parsed)) {
          restoredOverride = parsed;
          setTravelSelection({ accountId, destination: restoredOverride });
        } else {
          await AsyncStorage.removeItem(scopedKey);
          setTravelSelection(null);
        }
      } catch {
        // Ignore invalid stored travel overrides.
      }
      if (!active) {
        return;
      }
      await checkPermissionAndLocation({ travelOverrideForEvaluation: restoredOverride });
    })();

    return () => {
      active = false;
    };
  }, [accountId, canUseTravelMode, travelAccessReady, travelEntitlementsQuery.isError, travelEntitlementsQuery.isSuccess]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      const becameActive = appStateRef.current !== 'active' && nextState === 'active';
      appStateRef.current = nextState;
      if (becameActive) {
        void checkPermissionAndLocation({ preserveReadyState: true });
      }
    });

    return () => {
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (!deviceLocation) return;
    void persistProfileLocation(deviceLocation);
  }, [
    auth.isAuthenticated,
    auth.isReady,
    auth.session?.user.id,
    deviceLocation?.city,
    deviceLocation?.country,
    deviceLocation?.latitude,
    deviceLocation?.longitude,
    deviceLocation?.state,
    deviceLocation?.timezone,
  ]);

  const value = useMemo<LocationGateContextValue>(() => {
    const effectiveLocation = travelModeOverride
      ? {
          ...travelModeOverride,
          source: 'travel' as const,
          label: `${travelModeOverride.label} (Travel Mode)`,
        }
      : deviceLocation
        ? {
            ...deviceLocation,
            source: 'device' as const,
            label: deviceLocation.city ?? 'Current Location',
          }
        : null;

    return {
      status,
      deviceLocation,
      effectiveLocation,
      travelModeOverride,
      canUseTravelMode,
      isTravelModeActive: Boolean(travelModeOverride),
      errorMessage,
      profileSyncError,
      requestDeviceLocation,
      recheckPermissionAndLocation,
      setTravelModeOverride,
    };
  }, [canUseTravelMode, deviceLocation, errorMessage, profileSyncError, status, travelModeOverride]);

  return <LocationGateContext.Provider value={value}>{children}</LocationGateContext.Provider>;
}

export function useLocationGate() {
  const value = useContext(LocationGateContext);
  if (!value) {
    throw new Error('useLocationGate must be used within LocationGateProvider');
  }
  return value;
}
