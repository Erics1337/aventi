import { BlurView } from 'expo-blur';
import { Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { EventCategory, EventVibeTag, FeedFilters } from '@aventi/contracts';

interface Props {
  visible: boolean;
  filters: FeedFilters;
  onClose: () => void;
  onApply: (filters: FeedFilters) => void;
  isPremium: boolean;
}

const DATE_OPTIONS: { label: string; value: FeedFilters['date'] }[] = [
  { label: 'Today', value: 'today' },
  { label: 'Tomorrow', value: 'tomorrow' },
  { label: 'This Weekend', value: 'weekend' },
  { label: 'This Week', value: 'week' },
];

const TIME_OPTIONS: { label: string; value: FeedFilters['timeOfDay'] }[] = [
  { label: 'Any Time', value: undefined },
  { label: 'Morning', value: 'morning' },
  { label: 'Afternoon', value: 'afternoon' },
  { label: 'Evening', value: 'evening' },
  { label: 'Late Night', value: 'night' },
];

const PRICE_OPTIONS: { label: string; value: FeedFilters['price'] }[] = [
  { label: 'Any Price', value: 'any' },
  { label: 'Free', value: 'free' },
  { label: 'Paid', value: 'paid' },
];

const RADIUS_OPTIONS = [5, 10, 25, 50, 100];
const VIBE_OPTIONS: { label: string; value: EventVibeTag }[] = [
  { label: 'Chill', value: 'chill' },
  { label: 'Energetic', value: 'energetic' },
  { label: 'Social', value: 'social' },
  { label: 'Date Night', value: 'romantic' },
  { label: 'Intimate', value: 'intimate' },
  { label: 'Solo-Friendly', value: 'solo-friendly' },
  { label: 'Family', value: 'family' },
  { label: 'Adventurous', value: 'adventurous' },
  { label: 'Underground', value: 'underground' },
  { label: 'Late Night', value: 'late-night' },
  { label: 'Live Music', value: 'live-music' },
  { label: 'Smart', value: 'intellectual' },
  { label: 'Wellness', value: 'wellness' },
  { label: 'Elevated', value: 'luxury' },
];
const CATEGORY_OPTIONS: { label: string; value: EventCategory }[] = [
  { label: 'Nightlife', value: 'nightlife' },
  { label: 'Dining', value: 'dining' },
  { label: 'Live Music', value: 'concerts' },
  { label: 'Comedy', value: 'comedy' },
  { label: 'Arts', value: 'experiences' },
  { label: 'Markets', value: 'markets' },
  { label: 'Wellness', value: 'wellness' },
  { label: 'Sports', value: 'sports' },
  { label: 'Outdoors', value: 'outdoors' },
  { label: 'Tech & Talks', value: 'tech' },
];

export function FilterSheet({ visible, filters, onClose, onApply, isPremium }: Props) {
  const canUseAdvancedFilters = isPremium;

  const handleDateChange = (date: FeedFilters['date']) => {
    onApply({ ...filters, date });
  };

  const handleTimeChange = (timeOfDay: FeedFilters['timeOfDay']) => {
    onApply({ ...filters, timeOfDay });
  };

  const handlePriceChange = (price: FeedFilters['price']) => {
    onApply({ ...filters, price });
  };

  const handleRadiusChange = (radiusMiles: number) => {
    onApply({ ...filters, radiusMiles });
  };

  const toggleVibe = (vibe: EventVibeTag) => {
    const current = filters.vibes ?? [];
    onApply({
      ...filters,
      vibes: current.includes(vibe) ? current.filter((item) => item !== vibe) : [...current, vibe],
    });
  };

  const toggleCategory = (category: EventCategory) => {
    const current = filters.categories ?? [];
    onApply({
      ...filters,
      categories: current.includes(category)
        ? current.filter((item) => item !== category)
        : [...current, category],
    });
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <BlurView intensity={60} tint="dark" style={{ flex: 1 }}>
        <View className="flex-1 justify-end">
          <View className="max-h-[85%] rounded-t-[28px] border-t border-white/10 bg-black/95">
            {/* Drag handle */}
            <View className="items-center py-3">
              <View className="h-1 w-10 rounded-full bg-white/20" />
            </View>

            {/* Header */}
            <View className="flex-row items-center justify-between px-5 pb-4">
              <Text className="text-lg font-bold uppercase tracking-[2px] text-white">Filters</Text>
              <Pressable
                onPress={onClose}
                className="h-8 w-8 items-center justify-center rounded-full bg-white/10 active:scale-95"
              >
                <Ionicons name="close" size={18} color="rgba(255,255,255,0.8)" />
              </Pressable>
            </View>

            <ScrollView className="px-5 pb-8" showsVerticalScrollIndicator={false}>
              {/* Date Section */}
              <View className="mb-6">
                <Text className="mb-3 text-[11px] uppercase tracking-[2px] text-white/50">Date</Text>
                <View className="flex-row flex-wrap gap-2">
                  {DATE_OPTIONS.map((option) => (
                    <Pressable
                      key={option.value}
                      onPress={() => handleDateChange(option.value)}
                      className={`rounded-full border px-4 py-2.5 ${
                        filters.date === option.value
                          ? 'border-[#A67CFF] bg-[#A67CFF]/20'
                          : 'border-white/15 bg-white/5'
                      }`}
                    >
                      <Text
                        className={`text-xs uppercase tracking-[1px] ${
                          filters.date === option.value ? 'text-[#A67CFF]' : 'text-white/70'
                        }`}
                      >
                        {option.label}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              {/* Time of Day Section */}
              <View className="mb-6">
                <Text className="mb-3 text-[11px] uppercase tracking-[2px] text-white/50">Time of Day</Text>
                <View className="flex-row flex-wrap gap-2">
                  {TIME_OPTIONS.map((option) => (
                    <Pressable
                      key={option.label}
                      onPress={() => handleTimeChange(option.value)}
                      className={`rounded-full border px-4 py-2.5 ${
                        filters.timeOfDay === option.value
                          ? 'border-[#A67CFF] bg-[#A67CFF]/20'
                          : 'border-white/15 bg-white/5'
                      }`}
                    >
                      <Text
                        className={`text-xs uppercase tracking-[1px] ${
                          filters.timeOfDay === option.value ? 'text-[#A67CFF]' : 'text-white/70'
                        }`}
                      >
                        {option.label}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              {/* Budget Section */}
              <View className="mb-6">
                <Text className="mb-3 text-[11px] uppercase tracking-[2px] text-white/50">Budget</Text>
                <View className="flex-row flex-wrap gap-2">
                  {PRICE_OPTIONS.map((option) => (
                    <Pressable
                      key={option.value}
                      onPress={() => handlePriceChange(option.value)}
                      className={`rounded-full border px-4 py-2.5 ${
                        filters.price === option.value
                          ? 'border-[#A67CFF] bg-[#A67CFF]/20'
                          : 'border-white/15 bg-white/5'
                      }`}
                    >
                      <Text
                        className={`text-xs uppercase tracking-[1px] ${
                          filters.price === option.value ? 'text-[#A67CFF]' : 'text-white/70'
                        }`}
                      >
                        {option.label}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              {/* Search Radius Section */}
              <View className="mb-6">
                <View className="mb-3 flex-row items-center gap-2">
                  <Text className="text-[11px] uppercase tracking-[2px] text-white/50">Search Radius</Text>
                  {!canUseAdvancedFilters && (
                    <View className="rounded-full bg-[#A67CFF]/20 px-2 py-0.5">
                      <Text className="text-[9px] uppercase tracking-[1px] text-[#A67CFF]">Premium</Text>
                    </View>
                  )}
                </View>
                <View className="flex-row flex-wrap gap-2">
                  {RADIUS_OPTIONS.map((miles) => (
                    <Pressable
                      key={miles}
                      onPress={() => canUseAdvancedFilters && handleRadiusChange(miles)}
                      className={`rounded-full border px-4 py-2.5 ${
                        filters.radiusMiles === miles
                          ? 'border-[#A67CFF] bg-[#A67CFF]/20'
                          : canUseAdvancedFilters
                            ? 'border-white/15 bg-white/5'
                            : 'border-white/8 bg-white/3'
                      }`}
                    >
                      <Text
                        className={`text-xs uppercase tracking-[1px] ${
                          filters.radiusMiles === miles
                            ? 'text-[#A67CFF]'
                            : canUseAdvancedFilters
                              ? 'text-white/70'
                              : 'text-white/40'
                        }`}
                      >
                        {miles} mi
                      </Text>
                    </Pressable>
                  ))}
                </View>
                {!canUseAdvancedFilters && (
                  <Text className="mt-2 text-[10px] text-white/40">
                    Upgrade to Unlimited to customize search radius
                  </Text>
                )}
              </View>

              <View className="mb-6">
                <Text className="mb-3 text-[11px] uppercase tracking-[2px] text-white/50">Vibe</Text>
                <View className="flex-row flex-wrap gap-2">
                  {VIBE_OPTIONS.map((option) => {
                    const selected = (filters.vibes ?? []).includes(option.value);
                    return (
                      <Pressable
                        key={option.value}
                        onPress={() => toggleVibe(option.value)}
                        className={`rounded-full border px-4 py-2.5 ${
                          selected ? 'border-[#A67CFF] bg-[#A67CFF]/20' : 'border-white/15 bg-white/5'
                        }`}
                      >
                        <Text
                          className={`text-xs uppercase tracking-[1px] ${
                            selected ? 'text-[#A67CFF]' : 'text-white/70'
                          }`}
                        >
                          {option.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              <View className="mb-6">
                <Text className="mb-3 text-[11px] uppercase tracking-[2px] text-white/50">Categories</Text>
                <View className="flex-row flex-wrap gap-2">
                  {CATEGORY_OPTIONS.map((option) => {
                    const selected = (filters.categories ?? []).includes(option.value);
                    return (
                      <Pressable
                        key={option.value}
                        onPress={() => toggleCategory(option.value)}
                        className={`rounded-full border px-4 py-2.5 ${
                          selected ? 'border-[#A67CFF] bg-[#A67CFF]/20' : 'border-white/15 bg-white/5'
                        }`}
                      >
                        <Text
                          className={`text-xs uppercase tracking-[1px] ${
                            selected ? 'text-[#A67CFF]' : 'text-white/70'
                          }`}
                        >
                          {option.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              {/* Bottom spacer */}
              <View className="h-8" />
            </ScrollView>
          </View>
        </View>
      </BlurView>
    </Modal>
  );
}
