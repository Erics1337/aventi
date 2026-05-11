'use client';

import { useEffect, useState } from 'react';

/** Matches `apps/mobile/app.json` android.package */
const DEFAULT_ANDROID_PACKAGE = 'com.crestcode.aventi';

const DEFAULT_PLAY_STORE_URL = `https://play.google.com/store/apps/details?id=${DEFAULT_ANDROID_PACKAGE}`;

export function getPlayStoreUrl(): string {
  const fromEnv = process.env.NEXT_PUBLIC_PLAY_STORE_URL?.trim();
  return fromEnv || DEFAULT_PLAY_STORE_URL;
}

/** Full App Store product URL, e.g. https://apps.apple.com/us/app/aventi/id1234567890 */
export function getIosAppStoreUrl(): string | null {
  const fromEnv = process.env.NEXT_PUBLIC_IOS_APP_STORE_URL?.trim();
  return fromEnv || null;
}

export type VisitorStorePlatform = 'ios' | 'android' | 'other';

/**
 * Best-effort client detection for store routing.
 * iPadOS Safari often reports as Macintosh; maxTouchPoints disambiguates.
 */
export function getVisitorStorePlatform(): VisitorStorePlatform {
  if (typeof navigator === 'undefined') return 'other';
  const ua = navigator.userAgent;
  if (/iPad|iPhone|iPod/i.test(ua)) return 'ios';
  const nav = navigator as Navigator & { maxTouchPoints?: number; userAgentData?: { platform?: string } };
  if (nav.userAgentData?.platform === 'iOS') return 'ios';
  if (/Macintosh/i.test(ua) && (nav.maxTouchPoints ?? 0) > 1) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  return 'other';
}

/**
 * App Store on iOS (when configured), Play on Android, /profile for desktop
 * or when the iOS listing URL is not set yet.
 */
export function resolveGetAppHref(): string {
  const platform = getVisitorStorePlatform();
  if (platform === 'ios') return getIosAppStoreUrl() ?? '/profile';
  if (platform === 'android') return getPlayStoreUrl();
  return '/profile';
}

export function useGetAppStoreHref(): string {
  const [href, setHref] = useState('/profile');

  useEffect(() => {
    setHref(resolveGetAppHref());
  }, []);

  return href;
}

export function isHttpUrl(href: string): boolean {
  return href.startsWith('http://') || href.startsWith('https://');
}
