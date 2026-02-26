import { Animated, Easing, Text, View } from 'react-native';
import { useEffect, useRef } from 'react';

export function LoadingConstruct({ label = 'Synthesizing your night...' }: { label?: string }) {
  const pulse = useRef(new Animated.Value(0.6)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.6, duration: 700, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    ).start();
  }, [pulse]);

  return (
    <View className="items-center justify-center rounded-[28px] border border-white/10 bg-white/5 p-8">
      <Animated.View style={{ opacity: pulse, transform: [{ scale: pulse }] }} className="mb-4 h-20 w-20 rounded-full border border-fuchsia-300/30 bg-fuchsia-400/10" />
      <Text className="text-center text-xs uppercase tracking-[2px] text-white/70">{label}</Text>
    </View>
  );
}
