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
}

const LocationGateContext = createContext<LocationGateContextValue | null>(null);

export const TRAVEL_MODE_PRESETS: readonly TravelModeOverride[] = [
  {
    id: 'nyc',
    label: 'New York City',
    city: 'New York',
    timezone: 'America/New_York',
    latitude: 40.7128,
    longitude: -74.006,
  },
  {
    id: 'miami',
    label: 'Miami',
    city: 'Miami',
    timezone: 'America/New_York',
    latitude: 25.7617,
    longitude: -80.1918,
  },
  {
    id: 'la',
    label: 'Los Angeles',
    city: 'Los Angeles',
    timezone: 'America/Los_Angeles',
    latitude: 34.0522,
    longitude: -118.2437,
  },
] as const;

function resolveLocalTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? null;
  } catch {
    return null;
  }
}

async function reverseGeocodeCity(latitude: number, longitude: number): Promise<string | null> {
  try {
    const results = await Location.reverseGeocodeAsync({ latitude, longitude });
    const first = results[0];
    return first?.city ?? first?.district ?? first?.subregion ?? null;
  } catch {
    return null;
  }
}

export function LocationGateProvider({ children }: PropsWithChildren) {
  const auth = useAuthSession();
  const [status, setStatus] = useState<LocationGateStatus>('checking');
  const [deviceLocation, setDeviceLocation] = useState<LocationPoint | null>(null);
  const [travelModeOverride, setTravelModeOverrideState] = useState<TravelModeOverride | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [profileSyncError, setProfileSyncError] = useState<string | null>(null);
  const lastSyncedSignature = useRef<string | null>(null);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);

  const persistProfileLocation = async (location: LocationPoint) => {
    if (!auth.isReady) {
      return;
    }
    // Anonymous and full-account sessions can sync profile data. Local guest fallback should not.
    if (!auth.isAuthenticated && auth.isSupabaseConfigured) {
      setProfileSyncError(null);
      return;
    }
    const signature = JSON.stringify({
      latitude: Number(location.latitude.toFixed(4)),
      longitude: Number(location.longitude.toFixed(4)),
      city: location.city ?? null,
      timezone: location.timezone ?? null,
    });
    if (signature === lastSyncedSignature.current) {
      return;
    }

    try {
      await aventiApi.updateMyLocation({
        latitude: location.latitude,
        longitude: location.longitude,
        city: location.city ?? null,
        timezone: location.timezone ?? null,
      });
      lastSyncedSignature.current = signature;
      setProfileSyncError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to sync profile location.';
      setProfileSyncError(message);
    }
  };

  const resolveCurrentPosition = async (allowDevFallback: boolean) => {
    try {
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;
      const [city, timezone] = await Promise.all([
        reverseGeocodeCity(latitude, longitude),
        Promise.resolve(resolveLocalTimezone()),
      ]);
      const location: LocationPoint = { latitude, longitude, city, timezone };

      startTransition(() => {
        setDeviceLocation(location);
        setStatus('ready');
        setErrorMessage(null);
      });
      void persistProfileLocation(location);
      return;
    } catch {
      if (allowDevFallback && __DEV__) {
        const devFallback: LocationPoint = {
          latitude: 30.2672,
          longitude: -97.7431,
          city: 'Austin',
          timezone: 'America/Chicago',
        };
        startTransition(() => {
          setDeviceLocation(devFallback);
          setStatus('ready');
          setErrorMessage('Using Austin fallback coordinates (development only).');
        });
        void persistProfileLocation(devFallback);
        return;
      }

      startTransition(() => {
        setStatus('error');
        setErrorMessage('Could not access current GPS coordinates. Check device location services and retry.');
      });
    }
  };

  const recheckPermissionAndLocation = async () => {
    try {
      setStatus('checking');
      const permission = await Location.getForegroundPermissionsAsync();

      if (permission.status === 'granted') {
        await resolveCurrentPosition(false);
        return;
      }

      setDeviceLocation(null);
      setStatus(permission.status === 'denied' ? 'denied' : 'needs-permission');
      if (permission.status === 'denied') {
        setErrorMessage('Location permission is required to initialize your local feed.');
      } else {
        setErrorMessage(null);
      }
    } catch {
      setStatus('error');
      setErrorMessage('Failed to check location permission. Retry in a moment.');
    }
  };

  const requestDeviceLocation = async () => {
    try {
      setStatus('checking');
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== 'granted') {
        setDeviceLocation(null);
        setStatus('denied');
        setErrorMessage('Location permission is required to initialize your local feed.');
        return;
      }
      await resolveCurrentPosition(true);
    } catch {
      setStatus('error');
      setErrorMessage('Unable to request location permission. Try again.');
    }
  };

  const setTravelModeOverride = async (override: TravelModeOverride | null) => {
    if (override && !deviceLocation) {
      setErrorMessage('Enable device location first. Travel Mode is an override, not initial setup.');
      return;
    }

    startTransition(() => {
      setTravelModeOverrideState(override);
      if (override) {
        setErrorMessage(null);
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
  };

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const stored = await AsyncStorage.getItem(TRAVEL_MODE_STORAGE_KEY);
        if (!active || !stored) {
          return;
        }
        const parsed = JSON.parse(stored) as Partial<TravelModeOverride>;
        if (
          typeof parsed.id === 'string' &&
          typeof parsed.label === 'string' &&
          typeof parsed.latitude === 'number' &&
          typeof parsed.longitude === 'number'
        ) {
          setTravelModeOverrideState({
            id: parsed.id,
            label: parsed.label,
            latitude: parsed.latitude,
            longitude: parsed.longitude,
            city: typeof parsed.city === 'string' ? parsed.city : null,
            timezone: typeof parsed.timezone === 'string' ? parsed.timezone : null,
          });
        }
      } catch {
        // Ignore invalid stored travel overrides.
      }
    })();

    void recheckPermissionAndLocation();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      const becameActive = appStateRef.current !== 'active' && nextState === 'active';
      appStateRef.current = nextState;
      if (becameActive) {
        void recheckPermissionAndLocation();
      }
    });

    return () => {
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (travelModeOverride && !deviceLocation && status !== 'checking') {
      setTravelModeOverrideState(null);
      void AsyncStorage.removeItem(TRAVEL_MODE_STORAGE_KEY);
    }
  }, [deviceLocation, status, travelModeOverride]);

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
      canUseTravelMode: Boolean(deviceLocation),
      isTravelModeActive: Boolean(travelModeOverride),
      errorMessage,
      profileSyncError,
      requestDeviceLocation,
      recheckPermissionAndLocation,
      setTravelModeOverride,
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
