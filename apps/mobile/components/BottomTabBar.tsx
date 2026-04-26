import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

type TabBarProps = {
  state: { index: number; routes: { key: string; name: string }[] };
  descriptors: Record<string, { options: { tabBarAccessibilityLabel?: string } }>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  navigation: any;
};

const TABS = [
  { name: 'index', label: 'DISCOVERY', icon: 'compass' as const },
  { name: 'search', label: 'SEARCH', icon: 'search' as const },
  { name: 'favorites', label: 'SAVED', icon: 'bookmark' as const },
  { name: 'profile', label: 'PROFILE', icon: 'person' as const },
] as const;

export function BottomTabBar({ state, descriptors, navigation }: TabBarProps) {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={{
        flexDirection: 'row',
        backgroundColor: '#0f0f0f',
        paddingBottom: insets.bottom + 8,
        paddingTop: 12,
        paddingHorizontal: 16,
        borderTopWidth: 0,
        alignItems: 'center',
        justifyContent: 'space-between',
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
                backgroundColor: '#2d0a4e',
                borderRadius: 20,
                paddingVertical: 10,
                paddingHorizontal: 16,
                marginHorizontal: 4,
              }}
            >
              <Ionicons name={tab.icon} size={18} color="#e8c6ff" />
              <Text
                style={{
                  color: '#e8c6ff',
                  fontSize: 12,
                  fontWeight: '700',
                  letterSpacing: 0.8,
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
            }}
          >
            <Ionicons name={tab.icon} size={20} color="#6b6b6b" />
            <Text
              style={{
                color: '#6b6b6b',
                fontSize: 10,
                fontWeight: '600',
                letterSpacing: 0.6,
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
