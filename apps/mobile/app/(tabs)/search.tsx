import { useMemo, useState } from 'react';
import { router } from 'expo-router';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import type { Destination, FeedFilters } from '@aventi/contracts';
import { useLocationGate } from '../../lib/location-gate';
import { defaultTravelDateRange, validateTravelDateRange } from '../../lib/travel-search';
import { TravelDestinationPicker } from '../../components/TravelDestinationPicker';

const RADIUS_OPTIONS = [5, 10, 25, 50, 100] as const;
const AGE_OPTIONS: Array<{ label: string; value: NonNullable<FeedFilters['premiumAgeRestriction']> }> = [
  { label: 'All ages', value: 'all' },
  { label: '18+', value: '18+' },
  { label: '21+', value: '21+' },
];

export default function SearchScreen() {
  const location = useLocationGate();
  const defaults = useMemo(() => defaultTravelDateRange(), []);
  const [destination, setDestination] = useState<Destination | null>(location.travelModeOverride);
  const [startDate, setStartDate] = useState(defaults.startDate);
  const [endDate, setEndDate] = useState(defaults.endDate);
  const [radiusMiles, setRadiusMiles] = useState<(typeof RADIUS_OPTIONS)[number]>(10);
  const [age, setAge] = useState<NonNullable<FeedFilters['premiumAgeRestriction']>>('all');
  const [error, setError] = useState<string | null>(null);

  if (!location.canUseTravelMode) {
    return (
      <View className="flex-1 items-center justify-center bg-black px-6">
        <Text className="text-xs uppercase tracking-[3px] text-[#A67CFF]">Aventi Unlimited</Text>
        <Text className="mt-3 text-center text-2xl font-bold uppercase tracking-[1.5px] text-white">Travel discovery</Text>
        <Text className="mt-3 text-center text-sm leading-6 text-white/65">Upgrade from Profile to search supported US destinations and plan a verified event feed up to 60 days ahead.</Text>
        <Pressable onPress={() => router.push('/(tabs)/profile')} className="mt-6 rounded-full bg-white px-5 py-3"><Text className="text-xs font-bold uppercase tracking-[1.4px] text-black">View plans</Text></Pressable>
      </View>
    );
  }

  const apply = async () => {
    if (!destination) {
      setError('Choose a US destination from the search results.');
      return;
    }
    const dateError = validateTravelDateRange({ startDate, endDate });
    if (dateError) {
      setError(dateError);
      return;
    }
    setError(null);
    await location.setTravelModeOverride({ ...destination });
    router.replace({ pathname: '/(tabs)', params: { destinationId: destination.id, startDate, endDate, radiusMiles: String(radiusMiles), premiumAgeRestriction: age } });
  };

  return (
    <ScrollView className="flex-1 bg-black px-4 pt-14" contentContainerStyle={{ paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
      <Text className="text-xs uppercase tracking-[3px] text-white/55">Travel Discovery</Text>
      <Text className="mt-2 text-3xl font-bold uppercase tracking-[2px] text-white">Find a destination</Text>
      <Text className="mt-2 text-sm leading-5 text-white/65">Search supported US cities and plan up to 60 days ahead.</Text>
      <View className="mt-6"><TravelDestinationPicker selectedDestination={destination} onSelect={(item) => { setDestination(item); setError(null); }} /></View>
      <Text className="mb-2 mt-6 text-xs uppercase tracking-[2px] text-white/55">Dates · 7 days maximum</Text>
      <View className="flex-row gap-2">
        <TextInput value={startDate} onChangeText={setStartDate} placeholder="YYYY-MM-DD" placeholderTextColor="rgba(255,255,255,0.35)" className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white" accessibilityLabel="Travel start date" />
        <TextInput value={endDate} onChangeText={setEndDate} placeholder="YYYY-MM-DD" placeholderTextColor="rgba(255,255,255,0.35)" className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white" accessibilityLabel="Travel end date" />
      </View>
      <Text className="mb-2 mt-6 text-xs uppercase tracking-[2px] text-white/55">Radius</Text>
      <View className="flex-row flex-wrap gap-2">{RADIUS_OPTIONS.map((value) => <Pressable key={value} onPress={() => setRadiusMiles(value)} className={`rounded-full border px-4 py-2.5 ${radiusMiles === value ? 'border-[#A67CFF] bg-[#A67CFF]/20' : 'border-white/15 bg-white/5'}`}><Text className="text-xs text-white">{value} mi</Text></Pressable>)}</View>
      <Text className="mb-2 mt-6 text-xs uppercase tracking-[2px] text-white/55">Age</Text>
      <View className="flex-row gap-2">{AGE_OPTIONS.map((option) => <Pressable key={option.value} onPress={() => setAge(option.value)} className={`flex-1 rounded-full border px-3 py-2.5 ${age === option.value ? 'border-[#A67CFF] bg-[#A67CFF]/20' : 'border-white/15 bg-white/5'}`}><Text className="text-center text-xs text-white">{option.label}</Text></Pressable>)}</View>
      {error ? <Text className="mt-4 text-sm text-rose-300">{error}</Text> : null}
      <Pressable onPress={() => void apply()} className="mt-6 rounded-full bg-white px-4 py-4 active:scale-[0.99]"><Text className="text-center text-sm font-bold uppercase tracking-[1.5px] text-black">Explore destination</Text></Pressable>
    </ScrollView>
  );
}
