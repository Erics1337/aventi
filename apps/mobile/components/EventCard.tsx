import { LinearGradient } from 'expo-linear-gradient';
import { ImageBackground, StyleSheet, Text, View } from 'react-native';
import type { EventCard as EventCardModel } from '@aventi/contracts';
import { categoryGradients } from '@aventi/design-tokens';

interface Props {
  event: EventCardModel;
}

export function EventCard({ event }: Props) {
  const gradient = categoryGradients[event.category] ?? categoryGradients.experiences;

  return (
    <View className="flex-1 overflow-hidden rounded-[28px] border border-white/10 bg-black">
      <ImageBackground
        source={{
          uri:
            event.imageUrl ??
            'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=1200&q=80',
        }}
        resizeMode="cover"
        className="flex-1 justify-end"
      >
        <LinearGradient
          colors={['transparent', 'rgba(0,0,0,0.88)']}
          style={{ padding: 20, paddingTop: 120 }}
        >
          <View className="mb-3 self-start overflow-hidden rounded-full border border-white/15 px-3 py-1">
            <LinearGradient
              colors={gradient as unknown as [string, string]}
              style={[StyleSheet.absoluteFillObject, { opacity: 0.18, borderRadius: 999 }]}
            />
            <Text className="text-xs font-semibold uppercase tracking-[2px] text-white/90">
              {event.category}
            </Text>
          </View>

          <Text className="text-3xl font-bold uppercase tracking-[1.5px] text-white">
            {event.title}
          </Text>
          <Text className="mt-1 text-base text-white/75">{event.venueName}</Text>
          <Text className="mt-1 text-sm text-white/65">{new Date(event.startsAt).toLocaleString()}</Text>

          <View className="mt-3 flex-row flex-wrap gap-2">
            {event.vibes.slice(0, 4).map((vibe) => (
              <View key={vibe} className="rounded-full border border-white/12 bg-white/5 px-3 py-1">
                <Text className="text-xs uppercase tracking-[1px] text-white/80">{vibe}</Text>
              </View>
            ))}
          </View>
        </LinearGradient>
      </ImageBackground>
    </View>
  );
}
