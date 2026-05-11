import { Animated, Easing, Text, View } from 'react-native';
import { useEffect, useRef } from 'react';
import { LinearGradient } from 'expo-linear-gradient';
import { aventiGradients } from '@aventi/design-tokens';

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
      className="h-1.5 overflow-hidden rounded-full bg-aventi-overlay"
    >
      <Animated.View
        style={{ width: width * 0.45, transform: [{ translateX }] }}
        className="h-full overflow-hidden rounded-full"
      >
        <LinearGradient
          colors={aventiGradients.primary as unknown as [string, string, string]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={{ height: '100%' }}
        />
      </Animated.View>
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
    <View className="items-center justify-center overflow-hidden rounded-aventi-sheet border border-aventi-border bg-aventi-glass p-8">
      <LinearGradient
        colors={aventiGradients.surfaceGlow as unknown as [string, string, string]}
        style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 }}
      />
      <Animated.View
        style={{ opacity: pulse, transform: [{ scale: pulse }] }}
        className="mb-4 h-20 w-20 overflow-hidden rounded-full border border-white/20"
      >
        <LinearGradient
          colors={aventiGradients.primary as unknown as [string, string, string]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={{ flex: 1, opacity: 0.7 }}
        />
      </Animated.View>
      <Text className="text-center text-xs uppercase tracking-[1.4px] text-white/80">{label}</Text>
      
      {showProgress && (
        <View className="mt-6">
          <LoadingProgressBar width={200} />
        </View>
      )}
    </View>
  );
}
