import type { ConfigContext, ExpoConfig } from 'expo/config';
import appJson from './app.json';
import { validateReleasePublicConfig, type NativePlatform } from './lib/public-config.ts';

function releaseOrigin(value: string | undefined): URL | null {
  if (!value) return null;
  const parsed = new URL(value);
  if (parsed.protocol !== 'https:') {
    throw new Error('EXPO_PUBLIC_WEB_URL must use HTTPS.');
  }
  return parsed;
}

export default ({ config }: ConfigContext): ExpoConfig => {
  const base = appJson.expo as ExpoConfig;
  const releaseProfile = process.env.EAS_BUILD_PROFILE;
  const mustValidateRelease = releaseProfile === 'preview' || releaseProfile === 'production';
  const buildPlatform = process.env.EAS_BUILD_PLATFORM;
  if (mustValidateRelease) {
    const platforms: NativePlatform[] = buildPlatform === 'ios' || buildPlatform === 'android'
      ? [buildPlatform]
      : ['ios', 'android'];
    for (const platform of platforms) validateReleasePublicConfig(process.env, platform);
  }
  const webOrigin = releaseOrigin(process.env.EXPO_PUBLIC_WEB_URL);
  const host = webOrigin?.host;

  return {
    ...config,
    ...base,
    extra: {
      ...config.extra,
      ...base.extra,
      webUrl: webOrigin?.origin,
    },
    ios: {
      ...base.ios,
      associatedDomains: host ? [`applinks:${host}`] : [],
    },
    android: {
      ...base.android,
      intentFilters: host
        ? [
            {
              action: 'VIEW',
              autoVerify: true,
              category: ['BROWSABLE', 'DEFAULT'],
              data: [{ scheme: 'https', host, pathPrefix: '/auth' }],
            },
          ]
        : [],
    },
  };
};
