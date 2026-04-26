import { Animated, Easing, Text, View } from 'react-native';
import { useEffect, useRef } from 'react';

export function LoadingProgressBar({ width = 200 }: { width?: number }) {
  const travel = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.timing(travel, {
        toValue: 1,
        duration: 1100,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
    );
    animation.start();

    return () => {
      animation.stop();
      travel.stopAnimation();
      travel.setValue(0);
    };
  }, [travel]);

  const translateX = travel.interpolate({
    inputRange: [0, 1],
    outputRange: [-width * 0.4, width * 0.55],
  });

  return (
    <View
      style={{ width }}
      className="h-1.5 overflow-hidden rounded-full bg-black/40"
    >
      <Animated.View
        style={{ width: width * 0.45, transform: [{ translateX }] }}
        className="h-full rounded-full bg-[#A67CFF]"
      />
    </View>
  );
}

export function LoadingConstruct({ label = 'Synthesizing your night...', showProgress = false }: { label?: string; showProgress?: boolean }) {
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
      
      {showProgress && (
        <View className="mt-6">
          <LoadingProgressBar width={200} />
        </View>
      )}
    </View>
  );
}
