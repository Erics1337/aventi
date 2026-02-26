import { BlurView } from 'expo-blur';
import type { PropsWithChildren } from 'react';
import { StyleSheet, View } from 'react-native';

interface GlassPanelProps extends PropsWithChildren {
  className?: string;
}

export function GlassPanel({ children, className }: GlassPanelProps) {
  return (
    <View className={className} style={styles.outer}>
      <BlurView intensity={22} tint="dark" style={styles.blur}>
        {children}
      </BlurView>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    borderRadius: 22,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  blur: {
    padding: 14,
  },
});
