import { AventiApiClient } from '@aventi/api-client';

export const aventiApi = new AventiApiClient({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000',
  getAccessToken: () => null,
});

export function createAventiApi(accessToken: string | null) {
  return new AventiApiClient({
    baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000',
    getAccessToken: () => accessToken,
  });
}
