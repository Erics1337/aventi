import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { aventiGradients } from '@aventi/design-tokens';

const QUICK_FILTERS = ['All', 'Tonight', 'This Weekend', 'Free', 'Live Music', 'Comedy', 'Wellness', 'Rooftops'];
const TRENDING = [
  { title: 'Sunset rooftop parties', meta: '14 near you', icon: 'sunny-outline' as const },
  { title: 'Live sets after dark', meta: '8 venues', icon: 'musical-notes-outline' as const },
  { title: 'Culture pop-ups', meta: 'New this week', icon: 'sparkles-outline' as const },
];

export default function SearchScreen() {
  return (
    <ScrollView
      className="flex-1 bg-aventi-canvas"
      contentInsetAdjustmentBehavior="automatic"
      showsVerticalScrollIndicator={false}
      contentContainerStyle={{ padding: 20, paddingTop: 56, paddingBottom: 120, gap: 18 }}
    >
      <View>
        <Text className="text-xs uppercase tracking-[2px] text-white/50">Aventi Search</Text>
        <Text className="mt-2 text-[30px] leading-[34px] text-white" style={{ fontFamily: 'Poppins_700Bold' }}>
          Find your next vibe.
        </Text>
      </View>

      <View className="overflow-hidden rounded-[24px] border border-aventi-border bg-aventi-glassStrong">
        <LinearGradient
          colors={aventiGradients.surfaceGlow as unknown as [string, string, string]}
          style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 }}
        />
        <View className="flex-row items-center gap-3 px-4 py-4">
          <Ionicons name="search" size={20} color="rgba(255,255,255,0.72)" />
          <TextInput
            placeholder="Search events, artists, venues..."
            placeholderTextColor="rgba(229,231,235,0.45)"
            className="flex-1 text-base text-white"
            style={{ minHeight: 44 }}
          />
        </View>
      </View>

      <View className="flex-row flex-wrap gap-2">
        {QUICK_FILTERS.map((filter, index) => (
          <Pressable
            key={filter}
            className={`rounded-full border px-4 py-2.5 ${
              index === 0 ? 'border-aventi-pink bg-aventi-pink/15' : 'border-aventi-border bg-white/5'
            }`}
          >
            <Text className={`text-xs font-semibold ${index === 0 ? 'text-white' : 'text-white/70'}`}>
              {filter}
            </Text>
          </Pressable>
        ))}
      </View>

      <View className="gap-3">
        <Text className="text-[11px] uppercase tracking-[1.4px] text-white/50">Trending nearby</Text>
        {TRENDING.map((item) => (
          <Pressable
            key={item.title}
            className="flex-row items-center gap-4 rounded-[22px] border border-aventi-border bg-aventi-glass px-4 py-4 active:scale-[0.99]"
          >
            <View className="h-12 w-12 items-center justify-center overflow-hidden rounded-full border border-white/15">
              <LinearGradient
                colors={aventiGradients.primary as unknown as [string, string, string]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, opacity: 0.72 }}
              />
              <Ionicons name={item.icon} size={21} color="white" />
            </View>
            <View className="flex-1">
              <Text className="text-base text-white" style={{ fontFamily: 'Poppins_600SemiBold' }}>
                {item.title}
              </Text>
              <Text className="mt-1 text-sm text-white/55">{item.meta}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color="rgba(255,255,255,0.42)" />
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}
