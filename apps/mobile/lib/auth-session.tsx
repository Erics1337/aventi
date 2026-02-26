import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Session } from '@supabase/supabase-js';
import { createContext, startTransition, useContext, useEffect, useMemo, useState } from 'react';
import type { PropsWithChildren } from 'react';
import { supabase } from './supabase';

const AUTH_PROMPT_DISMISSED_KEY = 'aventi.auth.prompt.dismissed.v1';

export type AuthPromptReason =
  | 'welcome'
  | 'favorites'
  | 'report'
  | 'sync'
  | 'premium'
  | 'premium-purchase'
  | 'premium-restore';

interface SignUpResult {
  emailConfirmationRequired: boolean;
}

interface AuthSessionContextValue {
  isReady: boolean;
  isAuthenticated: boolean;
  isGuest: boolean;
  isAnonymousUser: boolean;
  isFullAccount: boolean;
  isLocalGuestMode: boolean;
  hasEnteredGuestMode: boolean;
  isSupabaseConfigured: boolean;
  email: string | null;
  session: Session | null;
  authPromptVisible: boolean;
  authPromptReason: AuthPromptReason;
  openAuthPrompt: (reason?: AuthPromptReason) => void;
  closeAuthPrompt: () => void;
  continueAsGuest: (captchaToken?: string) => Promise<void>;
  requireAuth: (reason: AuthPromptReason) => boolean;
  requireSessionBackedGuestOrAccount: (reason: Extract<AuthPromptReason, 'favorites' | 'report' | 'sync'>) => boolean;
  requireFullAccount: (reason: Extract<AuthPromptReason, 'premium' | 'premium-purchase' | 'premium-restore'>) => boolean;
  signInWithPassword: (email: string, password: string, captchaToken?: string) => Promise<void>;
  signUpWithPassword: (email: string, password: string, captchaToken?: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
}

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

function isAnonymousSession(session: Session | null): boolean {
  if (!session) return false;
  const user = session.user as Session['user'] & { is_anonymous?: boolean };
  if (user.is_anonymous === true) return true;
  const provider = user.app_metadata?.provider;
  return provider === 'anonymous';
}

async function markAuthPromptDismissed() {
  try {
    await AsyncStorage.setItem(AUTH_PROMPT_DISMISSED_KEY, '1');
  } catch {
    // Ignore storage failures; auth UX still works without persistence.
  }
}

export function AuthSessionProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [authPromptVisible, setAuthPromptVisible] = useState(false);
  const [authPromptReason, setAuthPromptReason] = useState<AuthPromptReason>('welcome');
  const [welcomeDismissed, setWelcomeDismissed] = useState(false);
  const isSupabaseConfigured = Boolean(supabase);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const stored = await AsyncStorage.getItem(AUTH_PROMPT_DISMISSED_KEY);
        if (active) {
          setWelcomeDismissed(stored === '1');
        }
      } catch {
        if (active) {
          setWelcomeDismissed(false);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    if (!supabase) {
      setIsReady(true);
      return () => {
        active = false;
      };
    }

    void (async () => {
      const { data } = await supabase.auth.getSession();
      if (!active) return;
      startTransition(() => {
        setSession(data.session ?? null);
        setIsReady(true);
      });
    })();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      startTransition(() => {
        setSession(nextSession ?? null);
        setIsReady(true);
      });
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isReady || session || welcomeDismissed) return;
    setAuthPromptReason('welcome');
    setAuthPromptVisible(true);
  }, [isReady, session, welcomeDismissed]);

  useEffect(() => {
    if (!session) return;
    setAuthPromptVisible(false);
    setWelcomeDismissed(true);
    void markAuthPromptDismissed();
  }, [session]);

  const value = useMemo<AuthSessionContextValue>(() => {
    const openAuthPrompt = (reason: AuthPromptReason = 'sync') => {
      setAuthPromptReason(reason);
      setAuthPromptVisible(true);
    };

    const closeAuthPrompt = () => {
      setAuthPromptVisible(false);
    };

    const continueAsGuest = async (captchaToken?: string) => {
      setWelcomeDismissed(true);
      await markAuthPromptDismissed();
      setAuthPromptVisible(false);
      if (!supabase || session) {
        return;
      }
      const { error } = await supabase.auth.signInAnonymously({
        options: {
          ...(captchaToken ? { captchaToken } : {}),
        },
      });
      if (error) {
        // Only fall back when anonymous auth is unavailable/unreachable, not when CAPTCHA is required.
        const message = `${error.message ?? ''}`.toLowerCase();
        if (message.includes('captcha')) {
          throw error;
        }
        return;
      }
    };

    const requireAuth = (reason: AuthPromptReason) => {
      if (session) return true;
      openAuthPrompt(reason);
      return false;
    };

    const requireSessionBackedGuestOrAccount = (
      reason: Extract<AuthPromptReason, 'favorites' | 'report' | 'sync'>,
    ) => {
      if (session) return true;
      openAuthPrompt(reason);
      return false;
    };

    const requireFullAccount = (
      reason: Extract<AuthPromptReason, 'premium' | 'premium-purchase' | 'premium-restore'>,
    ) => {
      if (session && !isAnonymousSession(session)) return true;
      openAuthPrompt(reason);
      return false;
    };

    const signInWithPassword = async (email: string, password: string, captchaToken?: string) => {
      if (!supabase) {
        throw new Error('Supabase auth is not configured in this build.');
      }
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
        options: {
          ...(captchaToken ? { captchaToken } : {}),
        },
      });
      if (error) {
        throw error;
      }
      setWelcomeDismissed(true);
      await markAuthPromptDismissed();
      setAuthPromptVisible(false);
    };

    const signUpWithPassword = async (
      email: string,
      password: string,
      captchaToken?: string,
    ): Promise<SignUpResult> => {
      if (!supabase) {
        throw new Error('Supabase auth is not configured in this build.');
      }
      if (isAnonymousSession(session)) {
        const { error } = await supabase.auth.updateUser({ email, password });
        if (error) {
          throw error;
        }
        setWelcomeDismissed(true);
        await markAuthPromptDismissed();
        setAuthPromptVisible(false);
        return { emailConfirmationRequired: false };
      }
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          ...(captchaToken ? { captchaToken } : {}),
        },
      });
      if (error) {
        throw error;
      }
      const emailConfirmationRequired = !data.session;
      if (!emailConfirmationRequired) {
        setWelcomeDismissed(true);
        await markAuthPromptDismissed();
        setAuthPromptVisible(false);
      }
      return { emailConfirmationRequired };
    };

    const signOut = async () => {
      if (!supabase) return;
      const { error } = await supabase.auth.signOut();
      if (error) {
        throw error;
      }
      setSession(null);
      setAuthPromptReason('sync');
      setAuthPromptVisible(false);
    };

    const anonymous = isAnonymousSession(session);

    return {
      isReady,
      isAuthenticated: Boolean(session),
      isGuest: !session || anonymous,
      isAnonymousUser: anonymous,
      isFullAccount: Boolean(session) && !anonymous,
      isLocalGuestMode: !session && welcomeDismissed,
      hasEnteredGuestMode: welcomeDismissed,
      isSupabaseConfigured,
      email: session?.user.email ?? null,
      session,
      authPromptVisible,
      authPromptReason,
      openAuthPrompt,
      closeAuthPrompt,
      continueAsGuest,
      requireAuth,
      requireSessionBackedGuestOrAccount,
      requireFullAccount,
      signInWithPassword,
      signUpWithPassword,
      signOut,
    };
  }, [authPromptReason, authPromptVisible, isReady, isSupabaseConfigured, session, welcomeDismissed]);

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession() {
  const value = useContext(AuthSessionContext);
  if (!value) {
    throw new Error('useAuthSession must be used within AuthSessionProvider');
  }
  return value;
}
