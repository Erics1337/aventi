import { Ionicons } from '@expo/vector-icons';
import { Pressable, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { aventiGradients } from '@aventi/design-tokens';

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
        className="h-[56px] w-[56px] overflow-hidden items-center justify-center rounded-full border border-white/15 bg-aventi-overlay"
        style={
          accent
            ? {
                boxShadow: `0 10px 28px ${accent}44`,
              }
            : undefined
        }
      >
        {accent ? (
          <LinearGradient
            colors={[accent, 'rgba(255,255,255,0.08)']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, opacity: 0.24 }}
          />
        ) : null}
        <Ionicons name={icon} size={24} color="#FFFFFF" />
      </View>
      <Text className="mt-1 text-[10px] uppercase tracking-[1.2px] text-white/80">{label}</Text>
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
    <View
      className="items-center gap-3 rounded-[22px] border border-aventi-border bg-aventi-overlay px-2 py-3"
      style={{ boxShadow: '0 18px 44px rgba(0,0,0,0.38)' }}
    >
      <LinearGradient
        colors={aventiGradients.surfaceGlow as unknown as [string, string, string]}
        style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, borderRadius: 22, opacity: 0.35 }}
      />
      <RailButton icon="close" label="Pass" onPress={onPass} accent="#B94A31" disabled={disabled} />
      <RailButton icon={saved ? 'heart' : 'heart-outline'} label={saved ? 'Saved' : 'Save'} onPress={onSave} accent="#E3AD43" disabled={disabled || saved} />
      <RailButton icon="information-circle-outline" label="Info" onPress={onInfo} />
      <RailButton icon="share-social-outline" label="Share" onPress={onShare} />
    </View>
  );
}
