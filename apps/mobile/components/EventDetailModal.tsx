import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { Linking, Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { EventCard } from '@aventi/contracts';
import { categoryGradients } from '@aventi/design-tokens';

interface Props {
  event: EventCard | null;
  visible: boolean;
  onClose: () => void;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }) + ' · ' + d.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function DetailRow({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  return (
    <View className="flex-row items-start gap-3 py-2">
      <View className="mt-0.5 h-8 w-8 items-center justify-center rounded-full bg-white/8">
        <Ionicons name={icon} size={16} color="rgba(255,255,255,0.7)" />
      </View>
      <View className="flex-1">
        <Text className="text-[11px] uppercase tracking-[1.5px] text-white/50">{label}</Text>
        <Text className="mt-0.5 text-sm font-medium text-white/90">{value}</Text>
      </View>
    </View>
  );
}

export function EventDetailModal({ event, visible, onClose }: Props) {
  if (!event) return null;

  const gradient = categoryGradients[event.category] ?? categoryGradients.experiences;
  const startsFormatted = formatDateTime(event.startsAt);
  const endsFormatted = event.endsAt ? formatDateTime(event.endsAt) : null;

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      onRequestClose={onClose}
    >
      <BlurView intensity={60} tint="dark" style={{ flex: 1 }}>
        <View className="flex-1 justify-end">
          <View className="max-h-[85%] rounded-t-[28px] border-t border-white/10 bg-black/95">
            {/* Header gradient bar */}
            <LinearGradient
              colors={gradient as unknown as [string, string]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={{ height: 3, borderTopLeftRadius: 28, borderTopRightRadius: 28 }}
            />

            {/* Drag handle */}
            <View className="items-center py-3">
              <View className="h-1 w-10 rounded-full bg-white/20" />
            </View>

            {/* Close button */}
            <Pressable
              onPress={onClose}
              className="absolute right-4 top-4 z-10 h-8 w-8 items-center justify-center rounded-full bg-white/10 active:scale-95"
            >
              <Ionicons name="close" size={18} color="rgba(255,255,255,0.8)" />
            </Pressable>

            <ScrollView className="px-6 pb-8" showsVerticalScrollIndicator={false}>
              {/* Category pill */}
              <View className="mb-3 self-start overflow-hidden rounded-full border border-white/15 px-3 py-1">
                <LinearGradient
                  colors={gradient as unknown as [string, string]}
                  style={{
                    position: 'absolute',
                    top: 0, left: 0, right: 0, bottom: 0,
                    opacity: 0.18,
                    borderRadius: 999,
                  }}
                />
                <Text className="text-xs font-semibold uppercase tracking-[2px] text-white/90">
                  {event.category}
                </Text>
              </View>

              {/* Title */}
              <Text className="text-2xl font-bold uppercase tracking-[1.5px] text-white">
                {event.title}
              </Text>

              {/* Description */}
              {event.description ? (
                <Text className="mt-3 text-base leading-6 text-white/70">
                  {event.description}
                </Text>
              ) : null}

              {/* Detail rows */}
              <View className="mt-5 rounded-2xl border border-white/8 bg-white/3 p-4">
                <DetailRow icon="location" label="Venue" value={event.venueName} />
                {event.city ? (
                  <DetailRow icon="navigate" label="City" value={event.city} />
                ) : null}
                <DetailRow icon="calendar" label="When" value={startsFormatted + (endsFormatted ? ` → ${endsFormatted}` : '')} />
                <DetailRow
                  icon="pricetag"
                  label="Price"
                  value={event.isFree ? 'Free' : (event.priceLabel ?? 'Check venue')}
                />
                {event.radiusMiles != null ? (
                  <DetailRow icon="compass" label="Distance" value={`${event.radiusMiles.toFixed(1)} mi away`} />
                ) : null}
              </View>

              {/* Vibes */}
              <View className="mt-5">
                <Text className="mb-2 text-[11px] uppercase tracking-[2px] text-white/50">Vibes</Text>
                <View className="flex-row flex-wrap gap-2">
                  {event.vibes.map((vibe) => (
                    <View key={vibe} className="rounded-full border border-white/12 bg-white/5 px-3 py-1.5">
                      <Text className="text-xs uppercase tracking-[1px] text-white/80">{vibe}</Text>
                    </View>
                  ))}
                </View>
              </View>

              {/* Booking CTA */}
              {event.bookingUrl ? (
                <Pressable
                  onPress={() => Linking.openURL(event.bookingUrl)}
                  className="mt-6 overflow-hidden rounded-full active:scale-[0.98]"
                >
                  <LinearGradient
                    colors={gradient as unknown as [string, string]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={{ paddingVertical: 16, alignItems: 'center', borderRadius: 999 }}
                  >
                    <Text className="text-sm font-bold uppercase tracking-[2px] text-white">
                      Get Tickets
                    </Text>
                  </LinearGradient>
                </Pressable>
              ) : null}

              {/* Bottom spacer for safe area */}
              <View className="h-8" />
            </ScrollView>
          </View>
        </View>
      </BlurView>
    </Modal>
  );
}
