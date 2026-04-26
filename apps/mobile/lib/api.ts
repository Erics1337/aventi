import { AventiApiClient } from '@aventi/api-client';
import { getSupabaseAccessTokenWithRecovery } from './auth-session';
import { resolveLocalhostUrl } from './localhost';

const defaultBaseUrl =
  resolveLocalhostUrl(process.env.EXPO_PUBLIC_API_BASE_URL) ?? 'http://127.0.0.1:8000';

export const aventiApi = new AventiApiClient({
  baseUrl: defaultBaseUrl,
  getAccessToken: getSupabaseAccessTokenWithRecovery,
});
