import { LinearGradient } from 'expo-linear-gradient';
import { ImageBackground, StyleSheet, Text, View } from 'react-native';
import type { EventCard as EventCardModel } from '@aventi/contracts';
import { aventiColors, aventiGradients, categoryGradients } from '@aventi/design-tokens';

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
    <View
      className="flex-1 overflow-hidden rounded-aventi-card border border-aventi-border bg-aventi-raised"
      style={{ boxShadow: '0 22px 58px rgba(0,0,0,0.42)' }}
    >
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
          colors={aventiGradients.surfaceGlow as unknown as [string, string, string]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={StyleSheet.absoluteFillObject}
        />
        <LinearGradient
          colors={['rgba(10,10,20,0.04)', 'rgba(10,10,20,0.34)', 'rgba(10,10,20,0.94)']}
          locations={[0, 0.42, 1]}
          style={{ padding: 20, paddingTop: 128 }}
        >
          <View className="mb-4 flex-row flex-wrap gap-2 self-start">
            <View className="overflow-hidden rounded-full border border-aventi-borderStrong px-3 py-1.5">
              <LinearGradient
                colors={gradient as unknown as [string, string]}
                style={[StyleSheet.absoluteFillObject, { opacity: 0.24, borderRadius: 999 }]}
              />
              <Text className="text-[11px] font-semibold uppercase tracking-[1.2px] text-white/95">
                {event.category}
              </Text>
            </View>
            {primaryVibe ? (
              <View className="rounded-full border border-white/15 bg-white/10 px-3 py-1.5">
                <Text className="text-[11px] uppercase tracking-[1px] text-white/85">{primaryVibe}</Text>
              </View>
            ) : null}
          </View>

          <Text
            selectable
            className="text-[30px] leading-[34px] text-white"
            style={{ fontFamily: 'Poppins_700Bold', textShadowColor: 'rgba(0,0,0,0.42)', textShadowRadius: 18 }}
          >
            {event.title}
          </Text>

          <View className="mt-2 flex-row items-center gap-2">
            <Text selectable className="text-base text-white/80" numberOfLines={1}>
              {event.venueName}
            </Text>
            {ratingText && (
              <Text className="text-sm text-aventi-orange">{ratingText}</Text>
            )}
          </View>

          <View className="mt-2 flex-row items-center gap-2">
            <Text className="text-sm text-white/70">
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
            <View className="mt-3 self-start overflow-hidden rounded-full border border-white/15 px-3 py-1.5">
              <LinearGradient
                colors={aventiGradients.primary as unknown as [string, string, string]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
                style={[StyleSheet.absoluteFillObject, { opacity: 0.18 }]}
              />
              <Text className="text-xs font-medium text-white/95">{priceText}</Text>
            </View>
          )}
          <View className="mt-3 flex-row flex-wrap gap-2">
            {secondaryVibes.slice(0, 3).map((vibe) => (
              <View key={vibe} className="rounded-full border border-white/15 bg-white/10 px-3 py-1">
                <Text className="text-xs uppercase tracking-[1px] text-white/80">{vibe}</Text>
              </View>
            ))}
          </View>
          <View className="mt-4 h-1 overflow-hidden rounded-full bg-white/10">
            <LinearGradient
              colors={[gradient[0], gradient[1], aventiColors.orange] as [string, string, string]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={{ height: '100%', width: '68%', borderRadius: 999 }}
            />
          </View>
        </LinearGradient>
      </ImageBackground>
    </View>
  );
}
