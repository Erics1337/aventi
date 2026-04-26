import { LinearGradient } from 'expo-linear-gradient';
import { ImageBackground, StyleSheet, Text, View } from 'react-native';
import type { EventCard as EventCardModel } from '@aventi/contracts';
import { categoryGradients } from '@aventi/design-tokens';

interface Props {
  event: EventCardModel;
}

function formatVenueRating(rating: number | null | undefined, reviewCount: number | null | undefined): string | null {
  if (typeof rating !== 'number' || !isFinite(rating)) return null;
  const clamped = Math.max(0, Math.min(5, rating));
  const rounded = Math.round(clamped);
  const stars = '★'.repeat(rounded) + '☆'.repeat(5 - rounded);
  return reviewCount ? `${stars} (${reviewCount})` : stars;
}

function formatPrice(event: EventCardModel): string {
  if (event.isFree) return 'Free';
  if (event.priceLabel) return event.priceLabel;
  if (event.ticketOffers && event.ticketOffers.length > 0) {
    const firstOffer = event.ticketOffers[0];
    if (firstOffer.isFree) return 'Free';
    if (firstOffer.priceLabel) return firstOffer.priceLabel;
  }
  return '';
}

export function EventCard({ event }: Props) {
  const gradient = categoryGradients[event.category] ?? categoryGradients.experiences;
  const ratingText = formatVenueRating(event.venueRating, event.venueReviewCount);
  const priceText = formatPrice(event);
  const [primaryVibe, ...secondaryVibes] = event.vibes ?? [];

  return (
    <View className="flex-1 overflow-hidden rounded-[28px] border border-white/10 bg-black">
      <ImageBackground
        source={{
          uri: event.imageUrl ??
            'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=800&h=1200&q=85',
          cache: 'force-cache',
        }}
        resizeMode="cover"
        className="flex-1 justify-end"
        imageStyle={{
          opacity: event.imageUrl ? 1 : 0.9,
        }}
      >
        <LinearGradient
          colors={['transparent', 'rgba(0,0,0,0.88)']}
          style={{ padding: 20, paddingTop: 120 }}
        >
          <View className="flex-row flex-wrap gap-2 self-start mb-3">
            <View className="overflow-hidden px-3 py-1 rounded-full border border-white/15">
              <LinearGradient
                colors={gradient as unknown as [string, string]}
                style={[StyleSheet.absoluteFillObject, { opacity: 0.18, borderRadius: 999 }]}
              />
              <Text className="text-xs font-semibold uppercase tracking-[2px] text-white/90">
                {event.category}
              </Text>
            </View>
            {primaryVibe ? (
              <View className="px-3 py-1 rounded-full border border-white/12 bg-white/5">
                <Text className="text-xs uppercase tracking-[1px] text-white/80">{primaryVibe}</Text>
              </View>
            ) : null}
          </View>

          <Text className="text-3xl font-bold uppercase tracking-[1.5px] text-white">
            {event.title}
          </Text>

          <View className="flex-row gap-2 items-center mt-1">
            <Text className="text-base text-white/75">{event.venueName}</Text>
            {ratingText && (
              <Text className="text-sm text-yellow-400/90">{ratingText}</Text>
            )}
          </View>

          <View className="flex-row gap-2 items-center mt-1">
            <Text className="text-sm text-white/65">
              {new Date(event.startsAt).toLocaleDateString(undefined, {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })}
            </Text>
            {event.endsAt && (
              <Text className="text-sm text-white/50">
                - {new Date(event.endsAt).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
              </Text>
            )}
          </View>

          {priceText && (
            <View className="self-start px-3 py-1 mt-2 rounded-full border border-white/12 bg-white/5">
              <Text className="text-xs font-medium text-white/90">{priceText}</Text>
            </View>
          )}
          <View className="flex-row flex-wrap gap-2 mt-3">
            {secondaryVibes.slice(0, 3).map((vibe) => (
              <View key={vibe} className="px-3 py-1 rounded-full border border-white/12 bg-white/5">
                <Text className="text-xs uppercase tracking-[1px] text-white/80">{vibe}</Text>
              </View>
            ))}
          </View>
        </LinearGradient>
      </ImageBackground>
    </View>
  );
}
