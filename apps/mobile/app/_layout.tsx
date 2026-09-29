import { Stack } from 'expo-router';
import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { pendingSwipeQueue } from '../lib/swipe-queue';
import { QueryClient, QueryClientProvider, focusManager, useQueryClient } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthSheet } from '../components/AuthSheet';
import { AuthSessionProvider, useAuthSession } from '../lib/auth-session';
import { LocationGateProvider } from '../lib/location-gate';
import 'react-native-gesture-handler';
import '../global.css';

const queryClient = new QueryClient();

function AccountScope() {
  const auth = useAuthSession();
  const client = useQueryClient();
  const previousId = useRef<string | null | undefined>(undefined);
  const accountId = auth.session?.user.id ?? null;
  useEffect(() => {
    if (!auth.isReady) return;
    if (previousId.current !== undefined && previousId.current !== accountId) {
      if (previousId.current) void pendingSwipeQueue.clearAccount(previousId.current);
      client.clear();
    }
    previousId.current = accountId;
  }, [accountId, auth.isReady, client]);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => focusManager.setFocused(state === 'active'));
    return () => subscription.remove();
  }, []);
  return null;
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthSessionProvider>
          <AccountScope />
          <LocationGateProvider>
            <StatusBar style="light" />
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: '#000000' },
                animation: 'fade',
              }}
            />
            <AuthSheet />
          </LocationGateProvider>
        </AuthSessionProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
