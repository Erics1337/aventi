import { Platform } from 'react-native';

export function resolveLocalhostUrl(url: string | undefined): string | undefined {
  if (!url) return url;
  if (Platform.OS === 'android') {
    return url.replace('127.0.0.1', '10.0.2.2').replace('localhost', '10.0.2.2');
  }
  return url;
}
