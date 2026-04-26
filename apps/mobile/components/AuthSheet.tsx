import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';
import { GlassPanel } from './GlassPanel';
import { formatAuthError, type AuthPromptReason, useAuthSession } from '../lib/auth-session';

type FormMode = 'signin' | 'signup';
const captchaSiteKey = process.env.EXPO_PUBLIC_HCAPTCHA_SITE_KEY;

const reasonCopy: Record<
  AuthPromptReason,
  {
    title: string;
    subtitle: string;
    eyebrow: string;
    guestHint: string;
  }
> = {
  welcome: {
    eyebrow: 'Optional Sign-In',
    title: 'Start in Guest Mode or Create Your Account',
    subtitle:
      'You can browse and swipe right away as a guest. Aventi can use an anonymous Supabase session so your profile persists on this device before you make an account.',
    guestHint:
      'We recommend creating a permanent account so you never lose your matches, and you can easily restore your premium access across devices.',
  },
  favorites: {
    eyebrow: 'Save Favorites',
    title: 'Save Favorites with Guest or Account',
    subtitle:
      'Guest mode can use a temporary anonymous account so hearts can persist on this device. Upgrade to a full account when you want durable recovery.',
    guestHint: 'Favorites require a real Supabase guest session or a full account.',
  },
  report: {
    eyebrow: 'Report Event',
    title: 'Start a Guest Session or Sign In to Report',
    subtitle:
      'Reporting is tied to authenticated users because the hide-after-3 rule depends on unique user reports. Anonymous guest auth is enough for this.',
    guestHint: 'Reports require a real Supabase guest session so each reporter stays unique.',
  },
  sync: {
    eyebrow: 'Sync Your Profile',
    title: 'Upgrade Your Guest Profile',
    subtitle:
      'Aventi can bootstrap an anonymous guest profile first, then you can upgrade to an email account to keep your swipes, preferences, and favorites across devices.',
    guestHint: 'Guest mode uses a real anonymous Supabase session before you upgrade.',
  },
  premium: {
    eyebrow: 'Premium Entitlements',
    title: 'Use a Full Account for Premium',
    subtitle:
      'Premium entitlements are server-authoritative in the PRD. Guest sessions stay on the free tier until you sign in or upgrade to a full account.',
    guestHint: 'You can continue browsing in guest mode with free-tier behavior.',
  },
  'premium-purchase': {
    eyebrow: 'Premium Upgrade',
    title: 'Create or Sign In to a Full Account',
    subtitle:
      'Premium purchase is tied to a permanent account so Aventi can safely apply and restore entitlements later.',
    guestHint:
      'Anonymous guest sessions can keep browsing and swiping, but premium checkout should start after account upgrade.',
  },
  'premium-restore': {
    eyebrow: 'Restore Premium',
    title: 'Full Account Required to Restore Purchases',
    subtitle:
      'Restore/lookup flows should run on a permanent account identity, not a temporary anonymous guest session.',
    guestHint: 'Upgrade your guest session or sign in to the account that owns the subscription.',
  },
};

function AuthButton({
  label,
  onPress,
  variant = 'secondary',
  disabled,
  loading,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost';
  disabled?: boolean;
  loading?: boolean;
}) {
  const className =
    variant === 'primary'
      ? 'rounded-2xl border border-white/20 bg-white px-4 py-3'
      : variant === 'secondary'
        ? 'rounded-2xl border border-white/20 bg-white/10 px-4 py-3'
        : 'rounded-2xl border border-white/10 bg-transparent px-4 py-3';

  const textClassName =
    variant === 'primary'
      ? 'text-center text-sm font-semibold uppercase tracking-[1.3px] text-black'
      : 'text-center text-sm font-semibold uppercase tracking-[1.3px] text-white';

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      className={`${className} ${(disabled || loading) ? 'opacity-50' : 'active:scale-[0.99]'}`}
    >
      {loading ? <ActivityIndicator color={variant === 'primary' ? '#000' : '#fff'} /> : <Text className={textClassName}>{label}</Text>}
    </Pressable>
  );
}

export function AuthSheet() {
  const auth = useAuthSession();
  const [formMode, setFormMode] = useState<FormMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorText, setErrorText] = useState<string | null>(null);
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [submitTask, setSubmitTask] = useState<'signin' | 'signup' | 'guest' | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(opacity, {
      toValue: auth.authPromptVisible ? 1 : 0,
      duration: 250,
      useNativeDriver: true,
    }).start();
  }, [auth.authPromptVisible, opacity]);

  // Auto-close welcome screen after successful guest sign-in
  useEffect(() => {
    if (auth.isAnonymousUser && auth.authPromptReason === 'welcome' && auth.authPromptVisible) {
      auth.closeAuthPrompt();
    }
  }, [auth.isAnonymousUser, auth.authPromptReason, auth.authPromptVisible, auth.closeAuthPrompt]);

  const copy = reasonCopy[auth.authPromptReason];
  const canCloseWithoutGuest = auth.isAuthenticated && auth.authPromptReason !== 'welcome';
  const createLabel = auth.isAnonymousUser ? 'Upgrade Guest Account' : 'Create Account';

  const handleGuestContinue = async () => {
    setErrorText(null);
    setNoticeText(null);
    setSubmitTask('guest');
    try {
      await auth.continueAsGuest();
    } catch (error) {
      setErrorText(formatAuthError(error));
    } finally {
      setSubmitTask(null);
    }
  };

  const handleSubmit = async () => {
    if (!email.trim() || !password) {
      setErrorText('Enter an email and password to continue.');
      return;
    }

    setErrorText(null);
    setNoticeText(null);
    setSubmitTask(formMode);

    try {
      if (formMode === 'signin') {
        await auth.signInWithPassword(email.trim(), password);
        return;
      }

      const result = await auth.signUpWithPassword(email.trim(), password);
      if (result.emailConfirmationRequired) {
        setNoticeText(auth.isAnonymousUser ? 'Guest profile upgraded. Check your email if confirmation is enabled.' : 'Check your email to confirm your account, then sign in.');
        setFormMode('signin');
      }
    } catch (error) {
      setErrorText(formatAuthError(error));
    } finally {
      setSubmitTask(null);
    }
  };

  return (
    <Animated.View
      pointerEvents={auth.authPromptVisible ? 'auto' : 'none'}
      className="absolute bottom-0 left-0 right-0 top-0 z-50 flex-1 elevation-50"
      style={{ opacity }}
    >
      <KeyboardAvoidingView
        behavior={Platform.select({ ios: 'padding', default: undefined })}
        className="flex-1 justify-end bg-black/90 px-4 pb-6 pt-16"
      >
        <GlassPanel>
          <View className="gap-4">
            <View className="flex-row items-start justify-between gap-4">
              <View className="flex-1">
                <Text className="text-[11px] uppercase tracking-[2px] text-white/50">{copy.eyebrow}</Text>
                <Text className="mt-2 text-2xl font-bold uppercase tracking-[1px] text-white">{copy.title}</Text>
                <Text className="mt-2 text-sm leading-5 text-white/70">{copy.subtitle}</Text>
              </View>
              {canCloseWithoutGuest ? (
                <Pressable
                  onPress={auth.closeAuthPrompt}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-2 active:scale-95"
                >
                  <Text className="text-[11px] font-semibold uppercase tracking-[1.2px] text-white/80">Later</Text>
                </Pressable>
              ) : null}
            </View>

            <View className="rounded-2xl border border-white/10 bg-white/5 p-3">
              <Text className="text-xs leading-5 text-white/70">{copy.guestHint}</Text>
            </View>

            <View className="flex-row gap-2">
              <Pressable
                onPress={() => {
                  setFormMode('signin');
                  setErrorText(null);
                  setNoticeText(null);
                }}
                className={`flex-1 rounded-xl border px-3 py-2 ${formMode === 'signin' ? 'border-white/20 bg-white/10' : 'border-white/10 bg-white/5'} active:scale-[0.99]`}
              >
                <Text className="text-center text-xs font-semibold uppercase tracking-[1.2px] text-white">
                  Sign In
                </Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  setFormMode('signup');
                  setErrorText(null);
                  setNoticeText(null);
                }}
                className={`flex-1 rounded-xl border px-3 py-2 ${formMode === 'signup' ? 'border-white/20 bg-white/10' : 'border-white/10 bg-white/5'} active:scale-[0.99]`}
              >
                <Text className="text-center text-xs font-semibold uppercase tracking-[1.2px] text-white">
                  {auth.isAnonymousUser ? 'Upgrade Guest' : 'Create Account'}
                </Text>
              </Pressable>
            </View>

            <View className="gap-2">
              <TextInput
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                placeholder="Email"
                placeholderTextColor="rgba(255,255,255,0.4)"
                className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-white"
              />
              <TextInput
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                autoCapitalize="none"
                autoComplete={formMode === 'signin' ? 'current-password' : 'new-password'}
                placeholder={formMode === 'signin' ? 'Password' : 'Password (min 6+)'}
                placeholderTextColor="rgba(255,255,255,0.4)"
                className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-white"
              />
              {auth.isAnonymousUser ? (
                <Text className="text-xs leading-5 text-white/60">
                  You are in a temporary guest session. Create Account upgrades this session. Sign In switches to an existing profile instead.
                </Text>
              ) : null}
              {!auth.isSupabaseConfigured ? (
                <Text className="text-xs leading-5 text-amber-200/90">
                  Supabase auth is not configured (`EXPO_PUBLIC_SUPABASE_URL` / `EXPO_PUBLIC_SUPABASE_ANON_KEY` missing). Guest access is blocked until this build is configured.
                </Text>
              ) : null}
              {auth.isSupabaseConfigured && !captchaSiteKey ? (
                <Text className="text-xs leading-5 text-white/50">
                  If you enable Supabase Auth CAPTCHA (recommended for anonymous sign-ins), add `EXPO_PUBLIC_HCAPTCHA_SITE_KEY` and a mobile hCaptcha challenge so auth requests can send `captchaToken`.
                </Text>
              ) : null}
              {errorText ?? auth.guestAuthError ? (
                <Text className="text-xs leading-5 text-rose-300/95">{errorText ?? auth.guestAuthError}</Text>
              ) : null}
              {noticeText ? (
                <Text className="text-xs leading-5 text-emerald-300/95">{noticeText}</Text>
              ) : null}
            </View>

            <View className="gap-2">
              <AuthButton
                label={formMode === 'signin' ? 'Sign In' : createLabel}
                onPress={() => {
                  void handleSubmit();
                }}
                variant="primary"
                disabled={!auth.isSupabaseConfigured}
                loading={submitTask === 'signin' || submitTask === 'signup'}
              />
              <AuthButton
                label={
                  auth.isAnonymousUser
                    ? 'Keep Temporary Guest Session'
                    : auth.guestAuthError
                      ? 'Retry Guest Access'
                      : auth.authPromptReason === 'welcome'
                        ? 'Continue as Guest'
                        : 'Keep Browsing as Guest'
                }
                onPress={() => {
                  void handleGuestContinue();
                }}
                variant="secondary"
                loading={submitTask === 'guest'}
              />
            </View>
          </View>
        </GlassPanel>
      </KeyboardAvoidingView>
    </Animated.View>
  );
}
