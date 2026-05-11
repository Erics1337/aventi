import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { aventiColors, aventiGradients } from '@aventi/design-tokens';

type TabBarProps = {
  state: { index: number; routes: { key: string; name: string }[] };
  descriptors: Record<string, { options: { tabBarAccessibilityLabel?: string } }>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  navigation: any;
};

const TABS = [
  { name: 'index', label: 'Discover', icon: 'compass' as const },
  { name: 'search', label: 'Search', icon: 'search' as const },
  { name: 'favorites', label: 'Saved', icon: 'bookmark' as const },
  { name: 'profile', label: 'Profile', icon: 'person' as const },
] as const;

export function BottomTabBar({ state, descriptors, navigation }: TabBarProps) {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={{
        flexDirection: 'row',
        backgroundColor: aventiColors.canvas,
        paddingBottom: insets.bottom + 8,
        paddingTop: 12,
        paddingHorizontal: 16,
        borderTopWidth: 1,
        borderTopColor: aventiColors.border,
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 -18px 44px rgba(0,0,0,0.34)',
      }}
    >
      {state.routes.map((route: { key: string; name: string }, index: number) => {
        const tab = TABS.find((t) => t.name === route.name);
        if (!tab) return null;

        const isFocused = state.index === index;
        const { options } = descriptors[route.key];

        const onPress = () => {
          const event = navigation.emit({
            type: 'tabPress',
            target: route.key,
            canPreventDefault: true,
          });
          if (!isFocused && !event.defaultPrevented) {
            navigation.navigate(route.name);
          }
        };

        if (isFocused) {
          return (
            <Pressable
              key={route.key}
              onPress={onPress}
              accessibilityRole="button"
              accessibilityState={{ selected: true }}
              accessibilityLabel={options.tabBarAccessibilityLabel}
              style={{
                flex: 1,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                borderRadius: 20,
                overflow: 'hidden',
                paddingVertical: 10,
                paddingHorizontal: 16,
                marginHorizontal: 4,
                minHeight: 44,
              }}
            >
              <LinearGradient
                colors={aventiGradients.primary as unknown as [string, string, string]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
                style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, opacity: 0.92 }}
              />
              <Ionicons name={tab.icon} size={18} color="#FFFFFF" />
              <Text
                style={{
                  color: '#FFFFFF',
                  fontSize: 11,
                  fontWeight: '700',
                  letterSpacing: 0,
                  fontFamily: 'Poppins_700Bold',
                }}
              >
                {tab.label}
              </Text>
            </Pressable>
          );
        }

        return (
          <Pressable
            key={route.key}
            onPress={onPress}
            accessibilityRole="button"
            accessibilityState={{ selected: false }}
            accessibilityLabel={options.tabBarAccessibilityLabel}
            style={{
              flex: 1,
              alignItems: 'center',
              justifyContent: 'center',
              paddingVertical: 10,
              marginHorizontal: 4,
              gap: 4,
              minHeight: 44,
            }}
          >
            <Ionicons name={tab.icon} size={20} color="rgba(229,231,235,0.62)" />
            <Text
              style={{
                color: 'rgba(229,231,235,0.62)',
                fontSize: 10,
                fontWeight: '600',
                letterSpacing: 0,
                fontFamily: 'Poppins_600SemiBold',
              }}
            >
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
