import { AventiApiClient } from '@aventi/api-client';

const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
const baseUrl: string = configuredBaseUrl ?? "";
if (!baseUrl || (process.env.NODE_ENV === 'production' && (!baseUrl.startsWith('https://') || /localhost|127\.0\.0\.1/.test(baseUrl)))) {
  throw new Error('NEXT_PUBLIC_API_BASE_URL must be configured; production requires a public HTTPS API.');
}

export const aventiApi = new AventiApiClient({
  baseUrl: baseUrl,
  getAccessToken: () => null,
});

export function createAventiApi(accessToken: string | null) {
  return new AventiApiClient({
    baseUrl: baseUrl,
    getAccessToken: () => accessToken,
  });
}
