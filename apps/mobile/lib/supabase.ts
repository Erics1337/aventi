import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { resolveLocalhostUrl } from './localhost';
import { requirePublicHttpsUrl } from './public-config';

declare const __DEV__: boolean;

const isReleaseRuntime = typeof __DEV__ === 'boolean' ? !__DEV__ : process.env.NODE_ENV === 'production';
const configuredSupabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const configuredSupabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY?.trim();
const supabaseUrl = isReleaseRuntime
  ? requirePublicHttpsUrl('EXPO_PUBLIC_SUPABASE_URL', configuredSupabaseUrl)
  : resolveLocalhostUrl(configuredSupabaseUrl);
const supabaseAnonKey = isReleaseRuntime
  ? configuredSupabaseAnonKey || (() => { throw new Error('EXPO_PUBLIC_SUPABASE_ANON_KEY is required for release builds.'); })()
  : configuredSupabaseAnonKey;

export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          storage: AsyncStorage,
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: false,
        },
      })
    : null;
