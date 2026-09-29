import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Pressable, Text, TextInput, View } from 'react-native';
import type { Destination } from '@aventi/contracts';
import { aventiApi } from '../lib/api';

interface Props {
  selectedDestination?: Destination | null;
  onSelect: (destination: Destination) => void | Promise<void>;
  enabled?: boolean;
}

export function TravelDestinationPicker({ selectedDestination, onSelect, enabled = true }: Props) {
  const [query, setQuery] = useState(selectedDestination?.label ?? '');
  const [debouncedQuery, setDebouncedQuery] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (selectedDestination?.label) setQuery(selectedDestination.label);
  }, [selectedDestination?.id, selectedDestination?.label]);

  const destinations = useQuery({
    queryKey: ['destinations', debouncedQuery],
    enabled: enabled && debouncedQuery.length >= 2,
    queryFn: () => aventiApi.searchDestinations(debouncedQuery),
    staleTime: 5 * 60_000,
  });

  return (
    <View>
      <TextInput
        value={query}
        onChangeText={setQuery}
        placeholder="City or destination"
        placeholderTextColor="rgba(255,255,255,0.35)"
        autoCapitalize="words"
        editable={enabled}
        className="rounded-2xl border border-white/15 bg-white/5 px-4 py-4 text-white disabled:opacity-40"
        accessibilityLabel="Search supported US destinations"
      />
      <View className="mt-2 gap-2">
        {destinations.data?.items.map((item) => (
          <Pressable
            key={item.id}
            onPress={() => void onSelect(item)}
            className={`rounded-2xl border px-4 py-3 ${selectedDestination?.id === item.id ? 'border-[#A67CFF] bg-[#A67CFF]/15' : 'border-white/10 bg-white/5'}`}
          >
            <Text className="font-semibold text-white">{item.label}</Text>
            <Text className="mt-1 text-xs uppercase tracking-[1px] text-white/50">{item.city}, {item.state} · US</Text>
          </Pressable>
        ))}
        {destinations.isFetching ? <Text className="text-xs text-white/50">Searching…</Text> : null}
        {!destinations.isFetching && destinations.isSuccess && destinations.data.items.length === 0 ? (
          <Text className="text-xs text-white/50">No supported US destinations matched that search.</Text>
        ) : null}
        {destinations.isError ? <Text className="text-xs text-rose-300">Destination search is unavailable. Try again.</Text> : null}
      </View>
    </View>
  );
}
