import { Ionicons } from '@expo/vector-icons';
import { Pressable, Text, View } from 'react-native';

interface FeedActionRailProps {
  onPass: () => void;
  onSave: () => void;
  onInfo: () => void;
  onShare: () => void;
  saved?: boolean;
  disabled?: boolean;
}

interface RailButtonProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  accent?: string;
  disabled?: boolean;
}

function RailButton({ icon, label, onPress, accent, disabled }: RailButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      className={`items-center ${disabled ? 'opacity-45' : 'active:scale-95'}`}
    >
      <View
        className="h-[58px] w-[58px] items-center justify-center rounded-full border border-white/15 bg-black/45"
        style={
          accent
            ? {
                shadowColor: accent,
                shadowOpacity: 0.28,
                shadowRadius: 12,
                shadowOffset: { width: 0, height: 4 },
              }
            : undefined
        }
      >
        <Ionicons name={icon} size={24} color="#FFFFFF" />
      </View>
      <Text className="mt-1 text-[10px] uppercase tracking-[1.2px] text-white/75">{label}</Text>
    </Pressable>
  );
}

export function FeedActionRail({
  onPass,
  onSave,
  onInfo,
  onShare,
  saved = false,
  disabled = false,
}: FeedActionRailProps) {
  return (
    <View className="items-center gap-3 rounded-[22px] border border-white/10 bg-black/35 px-2 py-3">
      <RailButton icon="close" label="Pass" onPress={onPass} accent="#FB7185" disabled={disabled} />
      <RailButton icon={saved ? 'heart' : 'heart-outline'} label={saved ? 'Saved' : 'Save'} onPress={onSave} accent="#7C3AED" disabled={disabled || saved} />
      <RailButton icon="information-circle-outline" label="Info" onPress={onInfo} />
      <RailButton icon="share-social-outline" label="Share" onPress={onShare} />
    </View>
  );
}
