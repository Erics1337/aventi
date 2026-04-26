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

const TRAVEL_MODE_STORAGE_KEY = 'aventi.travel.override.v1';

export type LocationGateStatus = 'checking' | 'needs-permission' | 'denied' | 'ready' | 'error';

export interface LocationPoint {
  latitude: number;
  longitude: number;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  timezone?: string | null;
}

export interface TravelModeOverride extends LocationPoint {
  id: string;
  label: string;
}

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
  setTravelModeCoordinates: (coordinates: {
    latitude: number;
    longitude: number;
    label?: string;
  }) => Promise<void>;
}

const LocationGateContext = createContext<LocationGateContextValue | null>(null);

export const TRAVEL_MODE_PRESETS: readonly TravelModeOverride[] = [
  {
    id: 'nyc',
    label: 'New York City',
    city: 'New York',
    state: 'NY',
    country: 'US',
    timezone: 'America/New_York',
    latitude: 40.7128,
    longitude: -74.006,
  },
  {
    id: 'miami',
    label: 'Miami',
    city: 'Miami',
    state: 'FL',
    country: 'US',
    timezone: 'America/New_York',
    latitude: 25.7617,
    longitude: -80.1918,
  },
  {
    id: 'la',
    label: 'Los Angeles',
    city: 'Los Angeles',
    state: 'CA',
    country: 'US',
    timezone: 'America/Los_Angeles',
    latitude: 34.0522,
    longitude: -118.2437,
  },
  {
    id: 'toronto',
    label: 'Toronto',
    city: 'Toronto',
    state: 'ON',
    country: 'CA',
    timezone: 'America/Toronto',
    latitude: 43.651070,
    longitude: -79.347015,
  },
] as const;

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

function formatCoordinateLabel(latitude: number, longitude: number): string {
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
}

async function buildTravelModeOverride(
  latitude: number,
  longitude: number,
  label?: string,
): Promise<TravelModeOverride> {
  const geocode = await reverseGeocodeLocation(latitude, longitude);
  const geocodeLabel = [geocode.city, geocode.state].filter(Boolean).join(', ');
  const nextLabel = label?.trim() || geocodeLabel || formatCoordinateLabel(latitude, longitude);

  return {
    id: `custom:${latitude.toFixed(4)},${longitude.toFixed(4)}`,
    label: nextLabel,
    latitude,
    longitude,
    city: geocode.city,
    state: geocode.state,
    country: geocode.country,
    timezone: null,
  };
}

export function LocationGateProvider({ children }: PropsWithChildren) {
  const auth = useAuthSession();
  const [status, setStatus] = useState<LocationGateStatus>('checking');
  const [deviceLocation, setDeviceLocation] = useState<LocationPoint | null>(null);
  const [travelModeOverride, setTravelModeOverrideState] = useState<TravelModeOverride | null>(null);
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
    const signature = JSON.stringify({
      latitude: Number(location.latitude.toFixed(4)),
      longitude: Number(location.longitude.toFixed(4)),
      city: location.city ?? null,
      state: location.state ?? null,
      country: location.country ?? null,
      timezone: location.timezone ?? null,
    });
    if (signature !== lastSyncedSignature.current) {
      try {
        await aventiApi.updateMyLocation({
          latitude: location.latitude,
          longitude: location.longitude,
          city: location.city ?? null,
          state: location.state ?? null,
          country: location.country ?? null,
          timezone: location.timezone ?? null,
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
    startTransition(() => {
      setTravelModeOverrideState(override);
      if (override || !deviceLocation) {
        setErrorMessage(null);
      }
      if (override && !deviceLocation) {
        setStatus('ready');
      }
    });

    try {
      if (override) {
        await AsyncStorage.setItem(TRAVEL_MODE_STORAGE_KEY, JSON.stringify(override));
      } else {
        await AsyncStorage.removeItem(TRAVEL_MODE_STORAGE_KEY);
      }
    } catch {
      // Ignore storage failures; override still works for the current session.
    }

    if (!override && !deviceLocation) {
      await checkPermissionAndLocation({ travelOverrideForEvaluation: null });
    }
  };

  const setTravelModeCoordinates = async ({
    latitude,
    longitude,
    label,
  }: {
    latitude: number;
    longitude: number;
    label?: string;
  }) => {
    const override = await buildTravelModeOverride(latitude, longitude, label);
    await setTravelModeOverride(override);
  };

  useEffect(() => {
    let active = true;

    void (async () => {
      let restoredOverride: TravelModeOverride | null = null;

      try {
        const stored = await AsyncStorage.getItem(TRAVEL_MODE_STORAGE_KEY);
        if (!active || !stored) {
          await checkPermissionAndLocation();
          return;
        }
        const parsed = JSON.parse(stored) as Partial<TravelModeOverride>;
        if (
          typeof parsed.id === 'string' &&
          typeof parsed.label === 'string' &&
          typeof parsed.latitude === 'number' &&
          typeof parsed.longitude === 'number'
        ) {
          restoredOverride = {
            id: parsed.id,
            label: parsed.label,
            latitude: parsed.latitude,
            longitude: parsed.longitude,
            city: typeof parsed.city === 'string' ? parsed.city : null,
            state: typeof parsed.state === 'string' ? parsed.state : null,
            country: typeof parsed.country === 'string' ? parsed.country : null,
            timezone: typeof parsed.timezone === 'string' ? parsed.timezone : null,
          };
          setTravelModeOverrideState(restoredOverride);
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
  }, []);

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
    const activeLocation = travelModeOverride ?? deviceLocation;
    if (!activeLocation) return;
    void persistProfileLocation(activeLocation);
  }, [
    auth.isAuthenticated,
    auth.isReady,
    deviceLocation?.city,
    deviceLocation?.country,
    deviceLocation?.latitude,
    deviceLocation?.longitude,
    deviceLocation?.state,
    deviceLocation?.timezone,
    travelModeOverride?.city,
    travelModeOverride?.country,
    travelModeOverride?.latitude,
    travelModeOverride?.longitude,
    travelModeOverride?.state,
    travelModeOverride?.timezone,
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
      canUseTravelMode: true,
      isTravelModeActive: Boolean(travelModeOverride),
      errorMessage,
      profileSyncError,
      requestDeviceLocation,
      recheckPermissionAndLocation,
      setTravelModeOverride,
      setTravelModeCoordinates,
    };
  }, [deviceLocation, errorMessage, profileSyncError, status, travelModeOverride]);

  return <LocationGateContext.Provider value={value}>{children}</LocationGateContext.Provider>;
}

export function useLocationGate() {
  const value = useContext(LocationGateContext);
  if (!value) {
    throw new Error('useLocationGate must be used within LocationGateProvider');
  }
  return value;
}
