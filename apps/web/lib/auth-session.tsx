'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase } from './supabase';

export type AuthPromptReason =
  | 'welcome'
  | 'favorites'
  | 'report'
  | 'sync'
  | 'premium'
  | 'premium-purchase'
  | 'premium-restore';

export type SignUpResult = { emailConfirmationRequired: boolean };

export interface AuthSessionContextValue {
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
  continueAsGuest: () => Promise<void>;
  requireAuth: (reason: AuthPromptReason) => boolean;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signUpWithPassword: (email: string, password: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
  isAdmin: boolean;
}

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

function isAnonymousSession(session: Session | null): boolean {
  if (!session) return false;
  const identities = session.user?.identities ?? [];
  return identities.length === 1 && identities[0]?.provider === 'anonymous';
}

function formatAuthError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return 'An unexpected error occurred.';
}

async function signInSupabaseGuest(): Promise<Session> {
  if (!supabase) {
    throw new Error('Supabase auth is not configured in this build.');
  }
  const { data, error } = await supabase.auth.signInAnonymously();
  if (error) {
    throw error;
  }
  if (!data.session) {
    throw new Error('Guest sign-in failed: no session returned.');
  }
  return data.session;
}

export function AuthSessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [authPromptVisible, setAuthPromptVisible] = useState(false);
  const [authPromptReason, setAuthPromptReason] = useState<AuthPromptReason>('welcome');
  const [guestAuthError, setGuestAuthError] = useState<string | null>(null);
  const isSupabaseConfigured = Boolean(supabase);

  useEffect(() => {
    let active = true;

    if (!supabase) {
      setGuestAuthError('Supabase auth is required in this build.');
      setIsReady(true);
      return () => {
        active = false;
      };
    }

    void (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (!active) return;
        setSession(data.session);
        setGuestAuthError(null);
        setIsReady(true);
      } catch (error) {
        if (!active) return;
        setSession(null);
        setGuestAuthError(formatAuthError(error));
        setAuthPromptReason('welcome');
        setAuthPromptVisible(true);
        setIsReady(true);
      }
    })();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession ?? null);
      if (nextSession) {
        setGuestAuthError(null);
        setAuthPromptVisible(false);
      }
      setIsReady(true);
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  // Only auto-open the auth prompt on the very first load when there is no session.
  // We track whether we've already done the initial check to avoid re-opening after sign-out.
  const [initialCheckDone, setInitialCheckDone] = useState(false);
  useEffect(() => {
    if (!isReady || initialCheckDone) return;
    setInitialCheckDone(true);
    // Don't auto-open — let the user choose to sign in via the header button.
    // (Remove forced prompt on page load so returning users aren't interrupted.)
  }, [isReady, initialCheckDone]);

  const openAuthPrompt = useCallback((reason: AuthPromptReason = 'sync') => {
    setAuthPromptReason(reason);
    setAuthPromptVisible(true);
  }, []);

  const closeAuthPrompt = useCallback(() => {
    setAuthPromptVisible(false);
  }, []);

  const continueAsGuest = useCallback(async () => {
    setGuestAuthError(null);
    if (session) {
      setAuthPromptVisible(false);
      return;
    }
    try {
      await signInSupabaseGuest();
      setGuestAuthError(null);
      setAuthPromptVisible(false);
    } catch (error) {
      setGuestAuthError(formatAuthError(error));
      setAuthPromptVisible(true);
      throw error;
    }
  }, [session]);

  const requireAuth = useCallback(
    (reason: AuthPromptReason) => {
      if (session) return true;
      openAuthPrompt(reason);
      return false;
    },
    [session, openAuthPrompt]
  );

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    if (!supabase) {
      throw new Error('Supabase auth is not configured in this build.');
    }
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) {
      throw error;
    }
    setGuestAuthError(null);
    setAuthPromptVisible(false);
  }, []);

  const signUpWithPassword = useCallback(
    async (email: string, password: string): Promise<SignUpResult> => {
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
    },
    [session]
  );

  const signOut = useCallback(async () => {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) {
      throw error;
    }
    setSession(null);
    setGuestAuthError(null);
    // Don't auto-reopen the auth modal after sign-out — user explicitly signed out.
  }, []);

  const isAdmin = useMemo(() => {
    if (!session) return false;
    const role = session.user?.app_metadata?.role;
    const roles = session.user?.app_metadata?.roles || [];
    return role === 'admin' || role === 'aventi_admin' || role === 'owner' ||
           roles.includes('admin') || roles.includes('aventi_admin') || roles.includes('owner');
  }, [session]);

  const value = useMemo<AuthSessionContextValue>(() => {
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
      signInWithPassword,
      signUpWithPassword,
      signOut,
      isAdmin,
    };
  }, [
    isReady,
    session,
    isSupabaseConfigured,
    guestAuthError,
    authPromptVisible,
    authPromptReason,
    openAuthPrompt,
    closeAuthPrompt,
    continueAsGuest,
    requireAuth,
    signInWithPassword,
    signUpWithPassword,
    signOut,
    isAdmin,
  ]);

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession(): AuthSessionContextValue {
  const context = useContext(AuthSessionContext);
  if (!context) {
    throw new Error('useAuthSession must be used within an AuthSessionProvider');
  }
  return context;
}
