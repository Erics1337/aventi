'use client';

import { useEffect, useState } from 'react';
import { Lock, X, Loader2, UserPlus, LogIn } from 'lucide-react';
import { useAuthSession, type AuthPromptReason } from '@/lib/auth-session';

type FormMode = 'signin' | 'signup';

const reasonCopy: Record<AuthPromptReason, { eyebrow: string; title: string; subtitle: string; guestHint: string }> = {
  welcome: {
    eyebrow: 'Get Started',
    title: 'Discover Events',
    subtitle: 'Sign in to save favorites, sync across devices, and unlock personalized recommendations.',
    guestHint: 'Or continue as a guest to browse events without creating an account.',
  },
  favorites: {
    eyebrow: 'Favorites',
    title: 'Save What You Love',
    subtitle: 'Sign in to save events to your favorites and access them on any device.',
    guestHint: 'Guest users can browse but cannot save favorites.',
  },
  report: {
    eyebrow: 'Report',
    title: 'Report an Issue',
    subtitle: 'Sign in to report content or issues. This helps us maintain quality and follow up with you.',
    guestHint: 'Guest users cannot submit reports.',
  },
  sync: {
    eyebrow: 'Sync',
    title: 'Sync Your Data',
    subtitle: 'Sign in to sync your preferences and favorites across all your devices.',
    guestHint: 'Guest sessions are temporary and limited to this device.',
  },
  premium: {
    eyebrow: 'Premium',
    title: 'Unlock Premium',
    subtitle: 'Sign in to access premium features and exclusive event access.',
    guestHint: 'Premium features require a full account.',
  },
  'premium-purchase': {
    eyebrow: 'Purchase',
    title: 'Complete Purchase',
    subtitle: 'Sign in to complete your premium purchase securely.',
    guestHint: 'Purchases require a full account for billing.',
  },
  'premium-restore': {
    eyebrow: 'Restore',
    title: 'Restore Purchases',
    subtitle: 'Sign in to restore your previous premium purchases.',
    guestHint: 'Account required to verify and restore purchases.',
  },
};

export function AuthModal() {
  const auth = useAuthSession();
  const [formMode, setFormMode] = useState<FormMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorText, setErrorText] = useState<string | null>(null);
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Reset form when modal opens
  useEffect(() => {
    if (auth.authPromptVisible) {
      setEmail('');
      setPassword('');
      setErrorText(null);
      setNoticeText(null);
      setFormMode('signin');
    }
  }, [auth.authPromptVisible]);

  // Auto-close welcome screen after successful guest sign-in
  useEffect(() => {
    if (auth.isAnonymousUser && auth.authPromptReason === 'welcome' && auth.authPromptVisible) {
      auth.closeAuthPrompt();
    }
  }, [auth.isAnonymousUser, auth.authPromptReason, auth.authPromptVisible, auth.closeAuthPrompt]);

  const copy = reasonCopy[auth.authPromptReason];
  const canCloseWithoutGuest = auth.isAuthenticated;
  const createLabel = auth.isAnonymousUser ? 'Upgrade Account' : 'Create Account';

  const handleGuestContinue = async () => {
    setErrorText(null);
    setNoticeText(null);
    setIsSubmitting(true);
    try {
      await auth.continueAsGuest();
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : 'Guest access failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!email.trim() || !password) {
      setErrorText('Enter an email and password to continue.');
      return;
    }

    setErrorText(null);
    setNoticeText(null);
    setIsSubmitting(true);

    try {
      if (formMode === 'signin') {
        await auth.signInWithPassword(email.trim(), password);
        return;
      }

      const result = await auth.signUpWithPassword(email.trim(), password);
      if (result.emailConfirmationRequired) {
        setNoticeText(
          auth.isAnonymousUser
            ? 'Guest profile upgraded. Check your email if confirmation is enabled.'
            : 'Check your email to confirm your account, then sign in.'
        );
        setFormMode('signin');
      }
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : 'Authentication failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!auth.authPromptVisible) return null;

  const tabBtn = (mode: FormMode) =>
    `border-0 rounded-md inline-flex items-center gap-2 min-h-[38px] px-[14px] font-bold text-[0.86rem] ${formMode === mode ? 'bg-[#195339] text-[#f1f1f1]' : 'bg-transparent text-[#171d1a]'}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(23,29,26,0.72)] backdrop-blur-[6px] p-4"
      onClick={() => { if (canCloseWithoutGuest) auth.closeAuthPrompt(); }}
    >
      <div
        className="relative w-full max-w-md rounded-xl border border-[rgba(23,29,26,0.12)] bg-[#f1f1f1] shadow-[0_24px_70px_rgba(23,29,26,0.28)] p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex gap-4 justify-between items-start mb-2">
          <div>
            <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#3a906a]">{copy.eyebrow}</span>
            <h2 className="mt-1 text-[1.8rem] leading-[1.1] font-bold text-[#171d1a]">{copy.title}</h2>
          </div>
          {canCloseWithoutGuest ? (
            <button
              className="w-9 h-9 rounded-lg border border-[rgba(23,29,26,0.14)] inline-grid place-items-center text-[rgba(23,29,26,0.6)] hover:bg-[rgba(23,29,26,0.06)]"
              onClick={auth.closeAuthPrompt}
              aria-label="Close"
            >
              <X size={20} />
            </button>
          ) : null}
        </div>

        <p className="text-[rgba(23,29,26,0.62)] leading-[1.65] mb-5">{copy.subtitle}</p>

        {!auth.isSupabaseConfigured ? (
          <div className="flex items-start gap-3 p-4 rounded-lg border border-[rgba(249,216,70,0.5)] bg-[rgba(249,216,70,0.12)]">
            <Lock size={20} className="shrink-0 mt-0.5 text-[#171d1a]" />
            <p className="m-0 text-[0.86rem] text-[rgba(23,29,26,0.72)] leading-[1.6]">Supabase auth is not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.</p>
          </div>
        ) : (
          <>
            <div className="p-3 rounded-lg bg-[rgba(23,29,26,0.05)] mb-5">
              <p className="m-0 text-[0.84rem] text-[rgba(23,29,26,0.62)]">{copy.guestHint}</p>
            </div>

            <div className="flex items-center gap-[6px] p-[5px] border border-[rgba(23,29,26,0.12)] rounded-lg mb-4">
              <button className={tabBtn('signin')} onClick={() => { setFormMode('signin'); setErrorText(null); setNoticeText(null); }}>
                <LogIn size={16} />
                Sign In
              </button>
              <button className={tabBtn('signup')} onClick={() => { setFormMode('signup'); setErrorText(null); setNoticeText(null); }}>
                <UserPlus size={16} />
                {createLabel}
              </button>
            </div>

            <form className="grid gap-3 mb-4" onSubmit={handleSubmit}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
                autoComplete="email"
                disabled={isSubmitting}
                className="min-h-[44px] border border-[rgba(23,29,26,0.18)] rounded-lg px-3 bg-white text-[#171d1a] placeholder:text-[rgba(23,29,26,0.38)] disabled:opacity-55"
              />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={formMode === 'signin' ? 'Password' : 'Password (min 6+)'}
                autoComplete={formMode === 'signin' ? 'current-password' : 'new-password'}
                disabled={isSubmitting}
                className="min-h-[44px] border border-[rgba(23,29,26,0.18)] rounded-lg px-3 bg-white text-[#171d1a] placeholder:text-[rgba(23,29,26,0.38)] disabled:opacity-55"
              />

              {auth.isAnonymousUser && (
                <p className="m-0 text-[0.82rem] text-[rgba(23,29,26,0.56)] leading-[1.55]">
                  You are in a temporary guest session. Create Account upgrades this session.
                  Sign In switches to an existing profile.
                </p>
              )}

              {errorText && <p className="m-0 text-[0.86rem] font-semibold text-[#c0392b]">{errorText}</p>}
              {noticeText && <p className="m-0 text-[0.86rem] font-semibold text-[#195339]">{noticeText}</p>}

              <button
                type="submit"
                className="border-0 rounded-lg inline-flex items-center justify-center gap-2 min-h-[44px] px-[18px] font-bold bg-[#f9d846] text-[#171d1a] disabled:opacity-55 disabled:cursor-not-allowed"
                disabled={isSubmitting || !email.trim() || !password}
              >
                {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
                {formMode === 'signin' ? 'Sign In' : createLabel}
              </button>
            </form>

            <div className="grid gap-3">
              <button
                type="button"
                className="border border-[rgba(23,29,26,0.14)] rounded-lg inline-flex items-center justify-center gap-2 min-h-[44px] px-[18px] font-bold bg-transparent text-[#171d1a] disabled:opacity-55 disabled:cursor-not-allowed"
                onClick={handleGuestContinue}
                disabled={isSubmitting}
              >
                {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
                {auth.isAnonymousUser
                  ? 'Keep Guest Session'
                  : auth.guestAuthError
                    ? 'Retry Guest Access'
                    : auth.authPromptReason === 'welcome'
                      ? 'Continue as Guest'
                      : 'Keep Browsing as Guest'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
