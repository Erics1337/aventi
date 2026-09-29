import type { Session } from '@supabase/supabase-js';
import * as Linking from 'expo-linking';
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
  passwordRecoveryPending: boolean;
  requestPasswordRecovery: (email: string) => Promise<void>;
  updateRecoveredPassword: (password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);
const captchaSiteKey = process.env.EXPO_PUBLIC_HCAPTCHA_SITE_KEY;
let reportGuestAuthFailure: ((error: unknown) => void) | null = null;

function authRedirectUrl(): string {
  const webUrl = process.env.EXPO_PUBLIC_WEB_URL?.replace(/\/$/, '');
  return webUrl ? `${webUrl}/auth/callback` : Linking.createURL('auth/callback');
}

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
  const [passwordRecoveryPending, setPasswordRecoveryPending] = useState(false);
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
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      startTransition(() => {
        setSession(nextSession ?? null);
        if (nextSession) {
          setGuestAuthError(null);
          setAuthPromptVisible(event === 'PASSWORD_RECOVERY');
        }
        if (event === 'PASSWORD_RECOVERY') {
          setPasswordRecoveryPending(true);
          setAuthPromptReason('welcome');
          setAuthPromptVisible(true);
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
    if (!supabase) return;
    const authClient = supabase;
    const handleAuthUrl = async (url: string) => {
      try {
        const parsed = new URL(url);
        const fragment = new URLSearchParams(parsed.hash.replace(/^#/, ''));
        const query = parsed.searchParams;
        const code = query.get('code');
        const accessToken = fragment.get('access_token') ?? query.get('access_token');
        const refreshToken = fragment.get('refresh_token') ?? query.get('refresh_token');
        const type = fragment.get('type') ?? query.get('type');
        if (code) {
          const { error } = await authClient.auth.exchangeCodeForSession(code);
          if (error) throw error;
        } else if (accessToken && refreshToken) {
          const { error } = await authClient.auth.setSession({ access_token: accessToken, refresh_token: refreshToken });
          if (error) throw error;
        } else {
          return;
        }
        if (type === 'recovery') {
          setPasswordRecoveryPending(true);
          setAuthPromptReason('welcome');
          setAuthPromptVisible(true);
        }
      } catch (error) {
        setGuestAuthError(formatAuthError(error));
        setAuthPromptVisible(true);
      }
    };
    void Linking.getInitialURL().then((url) => {
      if (url) void handleAuthUrl(url);
    });
    const subscription = Linking.addEventListener('url', ({ url }) => {
      void handleAuthUrl(url);
    });
    return () => subscription.remove();
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
        const { data, error } = await supabase.auth.updateUser(
          { email, password },
          { emailRedirectTo: authRedirectUrl() },
        );
        if (error) {
          throw error;
        }
        const emailConfirmationRequired = data.user.email?.toLowerCase() !== email.toLowerCase();
        if (!emailConfirmationRequired) {
          setGuestAuthError(null);
          setAuthPromptVisible(false);
        }
        return { emailConfirmationRequired };
      }
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: authRedirectUrl(),
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
        await clearLocalSupabaseSession();
      }
      setSession(null);
      setGuestAuthError(null);
      setAuthPromptReason('welcome');
      setAuthPromptVisible(true);
    };

    const requestPasswordRecovery = async (email: string) => {
      if (!supabase) throw new Error('Supabase auth is not configured in this build.');
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: authRedirectUrl(),
      });
      if (error) throw error;
    };

    const updateRecoveredPassword = async (password: string) => {
      if (!supabase) throw new Error('Supabase auth is not configured in this build.');
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setPasswordRecoveryPending(false);
      setAuthPromptVisible(false);
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
      passwordRecoveryPending,
      requestPasswordRecovery,
      updateRecoveredPassword,
      signOut,
    };
  }, [authPromptReason, authPromptVisible, guestAuthError, isReady, isSupabaseConfigured, passwordRecoveryPending, session]);

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession() {
  const value = useContext(AuthSessionContext);
  if (!value) {
    throw new Error('useAuthSession must be used within AuthSessionProvider');
  }
  return value;
}
