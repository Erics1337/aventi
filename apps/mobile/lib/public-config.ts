export type NativePlatform = 'ios' | 'android';

export interface ReleasePublicConfig {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
  webUrl: string;
  revenueCatApiKey: string;
}

function isLocalHostname(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (host === 'localhost' || host === '0.0.0.0' || host === '::1' || host.endsWith('.localhost') || host.endsWith('.local')) return true;
  if (/^127\./.test(host) || /^10\./.test(host) || /^192\.168\./.test(host)) return true;
  const match = /^172\.(\d+)\./.exec(host);
  return match ? Number(match[1]) >= 16 && Number(match[1]) <= 31 : false;
}

export function requirePublicHttpsUrl(name: string, value: string | undefined): string {
  if (!value?.trim()) throw new Error(`${name} is required for release builds.`);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid HTTPS URL.`);
  }
  if (parsed.protocol !== 'https:' || isLocalHostname(parsed.hostname)) {
    throw new Error(`${name} must use a public HTTPS origin in release builds.`);
  }
  if (parsed.username || parsed.password) throw new Error(`${name} must not contain URL credentials.`);
  if ((parsed.pathname && parsed.pathname !== '/') || parsed.search || parsed.hash) {
    throw new Error(`${name} must be an origin without a path, query, or fragment.`);
  }
  return parsed.origin;
}

export function validateReleasePublicConfig(
  environment: Record<string, string | undefined>,
  platform: NativePlatform,
): ReleasePublicConfig {
  const supabaseAnonKey = environment.EXPO_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!supabaseAnonKey) throw new Error('EXPO_PUBLIC_SUPABASE_ANON_KEY is required for release builds.');
  const nativeKeyName = platform === 'ios'
    ? 'EXPO_PUBLIC_REVENUECAT_IOS_API_KEY'
    : 'EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY';
  const revenueCatApiKey = environment[nativeKeyName]?.trim();
  if (!revenueCatApiKey) throw new Error(`${nativeKeyName} is required for release builds.`);
  return {
    apiBaseUrl: requirePublicHttpsUrl('EXPO_PUBLIC_API_BASE_URL', environment.EXPO_PUBLIC_API_BASE_URL),
    supabaseUrl: requirePublicHttpsUrl('EXPO_PUBLIC_SUPABASE_URL', environment.EXPO_PUBLIC_SUPABASE_URL),
    supabaseAnonKey,
    webUrl: requirePublicHttpsUrl('EXPO_PUBLIC_WEB_URL', environment.EXPO_PUBLIC_WEB_URL),
    revenueCatApiKey,
  };
}
