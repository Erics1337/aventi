import { Stack } from 'expo-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthSheet } from '../components/AuthSheet';
import { AuthSessionProvider } from '../lib/auth-session';
import { LocationGateProvider } from '../lib/location-gate';
import 'react-native-gesture-handler';
import '../global.css';

const queryClient = new QueryClient();

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthSessionProvider>
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
