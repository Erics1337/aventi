import { Ionicons } from '@expo/vector-icons';
import { Pressable, Text, View } from 'react-native';

interface SwipeActionsProps {
  onPass: () => void;
  onLike: () => void;
  onInfo?: () => void;
}

function CircleButton({ icon, label, onPress, accent }: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void; accent?: string }) {
  return (
    <Pressable onPress={onPress} className="items-center active:scale-95">
      <View
        className="h-[60px] w-[60px] items-center justify-center rounded-full border border-white/15 bg-white/10"
        style={accent ? { shadowColor: accent, shadowOpacity: 0.35, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } } : undefined}
      >
        <Ionicons name={icon} size={26} color="#FFFFFF" />
      </View>
      <Text className="mt-2 text-[11px] uppercase tracking-[1.5px] text-white/65">{label}</Text>
    </Pressable>
  );
}

export function SwipeActions({ onPass, onLike, onInfo }: SwipeActionsProps) {
  return (
    <View className="flex-row items-end justify-center gap-7 px-6 pb-4 pt-3">
      <CircleButton icon="close" label="Pass" onPress={onPass} accent="#FB7185" />
      <CircleButton icon="information" label="Info" onPress={onInfo ?? (() => undefined)} />
      <CircleButton icon="heart" label="Save" onPress={onLike} accent="#7C3AED" />
    </View>
  );
}
