import { AventiApiClient } from '@aventi/api-client';
import { supabase } from './supabase';

const defaultBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const aventiApi = new AventiApiClient({
  baseUrl: defaultBaseUrl,
  getAccessToken: async () => {
    if (!supabase) {
      return null;
    }
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  },
});
