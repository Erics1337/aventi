import { useEffect } from 'react';
import { router } from 'expo-router';
import { Text, View } from 'react-native';
import { useAuthSession } from '../../lib/auth-session';

export default function AuthCallbackScreen() {
  const auth = useAuthSession();

  useEffect(() => {
    if (auth.isReady && auth.isAuthenticated) {
      router.replace('/(tabs)');
    }
  }, [auth.isAuthenticated, auth.isReady]);

  return (
    <View className="flex-1 items-center justify-center bg-black px-6">
      <Text className="text-xs uppercase tracking-[3px] text-[#A67CFF]">Aventi account</Text>
      <Text className="mt-3 text-center text-xl font-semibold text-white">Confirming your secure sign-in…</Text>
      {auth.guestAuthError ? <Text className="mt-3 text-center text-sm text-rose-300">{auth.guestAuthError}</Text> : null}
    </View>
  );
}
