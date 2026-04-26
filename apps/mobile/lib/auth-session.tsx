import type { Session } from '@supabase/supabase-js';
import { createContext, startTransition, useContext, useEffect, useMemo, useState } from 'react';
import type { PropsWithChildren } from 'react';
import { supabase } from './supabase';

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
  isSupabaseConfigured: boolean;
  email: string | null;
  session: Session | null;
  guestAuthError: string | null;
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
const captchaSiteKey = process.env.EXPO_PUBLIC_HCAPTCHA_SITE_KEY;
let reportGuestAuthFailure: ((error: unknown) => void) | null = null;

function isAnonymousSession(session: Session | null): boolean {
  if (!session) return false;
  const user = session.user as Session['user'] & { is_anonymous?: boolean };
  if (user.is_anonymous === true) return true;
  const provider = user.app_metadata?.provider;
  return provider === 'anonymous';
}

function authErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Authentication failed';
}

export function formatAuthError(error: unknown): string {
  const message = authErrorMessage(error);
  if (message.toLowerCase().includes('captcha')) {
    return captchaSiteKey
      ? 'CAPTCHA is enabled for Supabase Auth, but this mobile build is not sending a CAPTCHA token yet. Wire the hCaptcha challenge before retrying.'
      : 'CAPTCHA is enabled for Supabase Auth. Add EXPO_PUBLIC_HCAPTCHA_SITE_KEY and wire an hCaptcha challenge in the mobile auth flow before retrying.';
  }
  return message;
}

export function isInvalidRefreshTokenError(error: unknown): boolean {
  const message = authErrorMessage(error).toLowerCase();
  return message.includes('invalid refresh token') || (message.includes('refresh token') && message.includes('not found'));
}

async function clearLocalSupabaseSession() {
  if (!supabase) return;
  try {
    await supabase.auth.signOut({ scope: 'local' });
  } catch {
    // Ignore sign-out failures while clearing a broken local session.
  }
}

async function signInSupabaseGuest(captchaToken?: string): Promise<Session> {
  if (!supabase) {
    throw new Error('Supabase auth is required in this build.');
  }

  const { data, error } = await supabase.auth.signInAnonymously({
    options: {
      ...(captchaToken ? { captchaToken } : {}),
    },
  });

  if (error) {
    throw error;
  }
  if (!data.session) {
    throw new Error('Supabase guest session did not return a valid session.');
  }
  return data.session;
}

async function recoverSupabaseGuestSession(error: unknown): Promise<Session> {
  await clearLocalSupabaseSession();
  try {
    return await signInSupabaseGuest();
  } catch (recoveryError) {
    reportGuestAuthFailure?.(recoveryError);
    throw recoveryError;
  }
}

export async function getSupabaseSessionWithRecovery(): Promise<Session | null> {
  if (!supabase) {
    return null;
  }

  const { data, error } = await supabase.auth.getSession();
  if (data.session) {
    return data.session;
  }
  if (!error) {
    return null;
  }
  if (!isInvalidRefreshTokenError(error)) {
    throw error;
  }
  return recoverSupabaseGuestSession(error);
}

export async function getSupabaseAccessTokenWithRecovery(): Promise<string | null> {
  if (!supabase) {
    return null;
  }

  try {
    const { data, error } = await supabase.auth.getSession();
    if (data.session?.access_token) {
      return data.session.access_token;
    }
    if (!error) {
      return null;
    }
    if (!isInvalidRefreshTokenError(error)) {
      throw error;
    }
    const recoveredSession = await recoverSupabaseGuestSession(error);
    return recoveredSession.access_token;
  } catch (error) {
    reportGuestAuthFailure?.(error);
    return null;
  }
}

export function AuthSessionProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [authPromptVisible, setAuthPromptVisible] = useState(false);
  const [authPromptReason, setAuthPromptReason] = useState<AuthPromptReason>('welcome');
  const [guestAuthError, setGuestAuthError] = useState<string | null>(null);
  const isSupabaseConfigured = Boolean(supabase);

  useEffect(() => {
    let active = true;
    reportGuestAuthFailure = (error) => {
      if (!active) return;
      startTransition(() => {
        setSession(null);
        setGuestAuthError(formatAuthError(error));
        setAuthPromptReason('welcome');
        setAuthPromptVisible(true);
        setIsReady(true);
      });
    };

    if (!supabase) {
      setGuestAuthError('Supabase auth is required in this build.');
      setIsReady(true);
      return () => {
        active = false;
        reportGuestAuthFailure = null;
      };
    }

    void (async () => {
      try {
        const nextSession = await getSupabaseSessionWithRecovery();
        if (!active) return;
        startTransition(() => {
          setSession(nextSession);
          setGuestAuthError(null);
          setIsReady(true);
        });
      } catch (error) {
        if (!active) return;
        startTransition(() => {
          setSession(null);
          setGuestAuthError(formatAuthError(error));
          setAuthPromptReason('welcome');
          setAuthPromptVisible(true);
          setIsReady(true);
        });
      }
    })();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      startTransition(() => {
        setSession(nextSession ?? null);
        if (nextSession) {
          setGuestAuthError(null);
          setAuthPromptVisible(false);
        }
        setIsReady(true);
      });
    });

    return () => {
      active = false;
      reportGuestAuthFailure = null;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isReady || session || authPromptVisible) return;
    setAuthPromptReason('welcome');
    setAuthPromptVisible(true);
  }, [authPromptVisible, isReady, session]);

  const value = useMemo<AuthSessionContextValue>(() => {
    const openAuthPrompt = (reason: AuthPromptReason = 'sync') => {
      setAuthPromptReason(reason);
      setAuthPromptVisible(true);
    };

    const closeAuthPrompt = () => {
      if (!session) {
        return;
      }
      setAuthPromptVisible(false);
    };

    const continueAsGuest = async (captchaToken?: string) => {
      setGuestAuthError(null);
      if (session) {
        setAuthPromptVisible(false);
        return;
      }
      try {
        await signInSupabaseGuest(captchaToken);
        setGuestAuthError(null);
        setAuthPromptVisible(false);
      } catch (error) {
        setGuestAuthError(formatAuthError(error));
        setAuthPromptVisible(true);
        throw error;
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
      setGuestAuthError(null);
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
        setGuestAuthError(null);
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
        setGuestAuthError(null);
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
      setGuestAuthError(null);
      setAuthPromptReason('welcome');
      setAuthPromptVisible(true);
    };

    const anonymous = isAnonymousSession(session);

    return {
      isReady,
      isAuthenticated: Boolean(session),
      isGuest: anonymous,
      isAnonymousUser: anonymous,
      isFullAccount: Boolean(session) && !anonymous,
      isSupabaseConfigured,
      email: session?.user.email ?? null,
      session,
      guestAuthError,
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
  }, [authPromptReason, authPromptVisible, guestAuthError, isReady, isSupabaseConfigured, session]);

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession() {
  const value = useContext(AuthSessionContext);
  if (!value) {
    throw new Error('useAuthSession must be used within AuthSessionProvider');
  }
  return value;
}
