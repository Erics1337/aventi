import assert from 'node:assert/strict';
import test from 'node:test';
import { requirePublicHttpsUrl, validateReleasePublicConfig } from '../lib/public-config';

const validEnvironment = {
  EXPO_PUBLIC_API_BASE_URL: 'https://api.aventi.example',
  EXPO_PUBLIC_SUPABASE_URL: 'https://project.supabase.co',
  EXPO_PUBLIC_SUPABASE_ANON_KEY: 'public-anon-key',
  EXPO_PUBLIC_WEB_URL: 'https://aventi.example',
  EXPO_PUBLIC_REVENUECAT_IOS_API_KEY: 'appl_public_key',
  EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY: 'goog_public_key',
};

test('release public config accepts complete HTTPS platform config', () => {
  const result = validateReleasePublicConfig(validEnvironment, 'ios');
  assert.equal(result.apiBaseUrl, 'https://api.aventi.example');
  assert.equal(result.webUrl, 'https://aventi.example');
  assert.equal(result.revenueCatApiKey, 'appl_public_key');
});

test('release URL validation rejects missing, HTTP, localhost, and private hosts', () => {
  assert.throws(() => requirePublicHttpsUrl('URL', undefined), /required/);
  assert.throws(() => requirePublicHttpsUrl('URL', 'http://api.example.com'), /public HTTPS/);
  assert.throws(() => requirePublicHttpsUrl('URL', 'https://localhost:8000'), /public HTTPS/);
  assert.throws(() => requirePublicHttpsUrl('URL', 'https://192.168.1.4'), /public HTTPS/);
});

test('release config requires Supabase and current-platform native keys', () => {
  assert.throws(
    () => validateReleasePublicConfig({ ...validEnvironment, EXPO_PUBLIC_SUPABASE_ANON_KEY: '' }, 'ios'),
    /SUPABASE_ANON_KEY/,
  );
  assert.throws(
    () => validateReleasePublicConfig({ ...validEnvironment, EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY: '' }, 'android'),
    /REVENUECAT_ANDROID_API_KEY/,
  );
});
