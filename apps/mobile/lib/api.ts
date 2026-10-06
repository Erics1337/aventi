import { AventiApiClient } from '@aventi/api-client';
import { getSupabaseAccessTokenWithRecovery } from './auth-session';
import { resolveLocalhostUrl } from './localhost';
import { requirePublicHttpsUrl } from './public-config';

declare const __DEV__: boolean;

const isReleaseRuntime = typeof __DEV__ === 'boolean' ? !__DEV__ : process.env.NODE_ENV === 'production';
const configuredBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;

const defaultBaseUrl =
  isReleaseRuntime
    ? requirePublicHttpsUrl('EXPO_PUBLIC_API_BASE_URL', configuredBaseUrl)
    : resolveLocalhostUrl(configuredBaseUrl) ?? 'http://127.0.0.1:8000';

export const aventiApi = new AventiApiClient({
  baseUrl: defaultBaseUrl,
  getAccessToken: getSupabaseAccessTokenWithRecovery,
});
