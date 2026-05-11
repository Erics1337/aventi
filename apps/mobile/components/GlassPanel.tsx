import { BlurView } from 'expo-blur';
import type { PropsWithChildren } from 'react';
import { StyleSheet, View } from 'react-native';
import { aventiColors } from '@aventi/design-tokens';

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
    borderRadius: 24,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: aventiColors.border,
    backgroundColor: aventiColors.glass,
    boxShadow: '0 14px 42px rgba(0,0,0,0.28)',
  },
  blur: {
    padding: 16,
  },
});
