'use client';

import { useEffect, useMemo, useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import {
  Activity,
  ArrowDown,
  Bell,
  CalendarDays,
  Check,
  ChevronDown,
  Compass,
  Eye,
  Filter,
  Gauge,
  Heart,
  Info,
  Loader2,
  Lock,
  LogOut,
  MapPin,
  Menu,
  Play,
  RefreshCcw,
  Search,
  Share2,
  ShieldCheck,
  Sparkles,
  User,
  X,
} from 'lucide-react';
import type {
  AdminDashboardResponse,
  AdminMarketSummary,
  EventCard,
  EventCategory,
  EventVibeTag,
  FeedFilters,
  SwipeAction,
} from '@aventi/contracts';
import {
  applySwipeAction,
  categoryLabels,
  demoEvents,
  heroImages,
  vibeLabels,
} from '@/lib/demo-data';
import { createAventiApi } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import { useAuthSession } from '@/lib/auth-session';
import { AuthModal } from './AuthModal';

const categoryOptions: EventCategory[] = ['nightlife', 'dining', 'concerts', 'experiences', 'wellness'];
const vibeOptions: EventVibeTag[] = ['social', 'live-music', 'romantic', 'wellness', 'late-night', 'intellectual'];

/** Marketing layout + surfaces — tied to `app/globals.css` @theme tokens. */
const ds = {
  wrap: 'mx-auto w-full max-w-[min(1200px,calc(100%-32px))]',
  section: 'px-[clamp(16px,4vw,72px)] py-[clamp(72px,11vw,132px)]',
  eyebrow: 'text-[0.72rem] font-bold uppercase tracking-[0.16em] text-mellow-yellow',
  h2: 'font-semibold tracking-tight text-black-grey text-[clamp(1.85rem,4vw,2.89rem)] leading-[1.1]',
  h2OnDark: 'font-semibold tracking-tight text-aventi-white text-[clamp(1.85rem,4vw,2.89rem)] leading-[1.1]',
  bodyMuted: 'text-[rgba(23,29,26,0.62)] leading-[1.75]',
  bodyOnDark: 'text-[rgba(241,241,241,0.78)] leading-[1.75]',
  heroOverlay:
    'absolute inset-0 bg-[linear-gradient(135deg,rgba(25,83,57,0.38),transparent_42%),linear-gradient(90deg,rgba(23,29,26,0.94),rgba(23,29,26,0.56)_52%,rgba(23,29,26,0.2)),linear-gradient(0deg,rgba(23,29,26,0.68),transparent_44%)]',
  statsStrip:
    'rounded-aventi-panel border border-aventi-white/18 bg-[rgba(23,29,26,0.78)] backdrop-blur-xl shadow-[0_28px_90px_rgba(0,0,0,0.38)] overflow-hidden',
  card: 'rounded-aventi-panel border border-black-grey/12 bg-white/60 shadow-[0_24px_70px_-14px_rgba(23,29,26,0.2)]',
  cardMuted: 'rounded-aventi-panel border border-black-grey/10 bg-white/45 backdrop-blur-sm',
  btnPrimary:
    'border-0 rounded-lg inline-flex items-center justify-center gap-2.5 min-h-11 px-5 font-bold bg-mellow-yellow text-black-grey transition-[opacity,transform] hover:opacity-95 active:scale-[0.99]',
  btnGhostOnDark:
    'border border-aventi-white/18 rounded-lg inline-flex items-center justify-center gap-2.5 min-h-11 px-5 font-bold bg-aventi-white/10 text-aventi-white hover:bg-aventi-white/14 transition-colors',
  linkAccent: 'border-b-2 border-dark-green/35 text-dark-green font-bold hover:border-dark-green transition-colors',
} as const;

function formatDateTime(value?: string | null) {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatEventTime(startsAt: string) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(startsAt));
}

function formatPrice(event: EventCard) {
  if (event.isFree) return 'Free';
  return event.priceLabel || event.ticketOffers?.[0]?.priceLabel || 'Check venue';
}

function marketStatus(market: AdminMarketSummary) {
  if (market.lastError) return 'attention';
  if (market.scanLockUntil && new Date(market.scanLockUntil).getTime() > Date.now()) return 'warming';
  if (market.lastTargetedRequestedAt && market.lastTargetedRequestedAt !== market.lastTargetedCompletedAt) {
    return 'targeted_warming';
  }
  return 'ready';
}

function LogoMark() {
  return (
    <a className="inline-flex items-center gap-3 min-h-[42px] text-[0.78rem] font-bold uppercase tracking-[0.18em]" href="/" aria-label="Aventi home">
      <img src="/brand/icon.png" alt="" className="w-9 h-9 rounded-lg" />
      <span>Aventi</span>
    </a>
  );
}

function NavMenu({
  open,
  onClose,
  active,
  theme = 'light',
}: {
  open: boolean;
  onClose: () => void;
  active?: 'feed' | 'admin';
  theme?: 'light' | 'dark';
}) {
  const auth = useAuthSession();

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Lock body scroll when open
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  const isDark = theme === 'dark';
  const panel = isDark
    ? 'bg-black-grey text-aventi-white border-[rgba(241,241,241,0.12)]'
    : 'bg-aventi-white text-black-grey border-[rgba(23,29,26,0.12)]';
  const divider = isDark ? 'border-[rgba(241,241,241,0.1)]' : 'border-[rgba(23,29,26,0.1)]';
  const linkBase = 'flex items-center gap-3 rounded-lg px-4 py-3 text-[1rem] font-bold transition-colors';
  const linkActive = isDark
    ? 'bg-[rgba(249,216,70,0.12)] text-mellow-yellow'
    : 'bg-[rgba(25,83,57,0.1)] text-dark-green';
  const linkIdle = isDark
    ? 'text-[rgba(241,241,241,0.78)] hover:bg-[rgba(241,241,241,0.07)]'
    : 'text-[rgba(23,29,26,0.72)] hover:bg-[rgba(23,29,26,0.06)]';
  const metaText = isDark ? 'text-[rgba(241,241,241,0.44)]' : 'text-[rgba(23,29,26,0.44)]';

  const navItems: { href: string; label: string; icon: React.ReactNode; key: string }[] = [
    { href: '/feed',   label: 'Event Feed',   icon: <Sparkles size={18} />,    key: 'feed' },
    ...(auth.isAdmin
      ? [{ href: '/admin', label: 'Admin Portal', icon: <ShieldCheck size={18} />, key: 'admin' }]
      : []),
  ];

  return (
    <div className="flex fixed inset-0 z-50 justify-end" aria-modal="true" role="dialog" aria-label="Navigation menu">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-[rgba(23,29,26,0.55)] backdrop-blur-[4px]"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className={`relative flex flex-col w-[min(340px,90vw)] h-full border-l ${panel} shadow-[-24px_0_70px_rgba(0,0,0,0.18)]`}>
        {/* Header */}
        <div className={`flex justify-between items-center px-5 py-4 border-b ${divider}`}>
          <LogoMark />
          <button
            className={`w-9 h-9 rounded-lg border inline-grid place-items-center ${isDark ? 'border-[rgba(241,241,241,0.17)] text-[rgba(241,241,241,0.7)]' : 'border-[rgba(23,29,26,0.14)] text-[rgba(23,29,26,0.6)]'}`}
            onClick={onClose}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex flex-col gap-1 px-3 py-4" aria-label="Menu navigation">
          {navItems.map((item) => (
            <a
              key={item.key}
              href={item.href}
              className={`${linkBase} ${active === item.key ? linkActive : linkIdle}`}
              onClick={onClose}
            >
              {item.icon}
              {item.label}
            </a>
          ))}
        </nav>

        <div className={`mx-3 border-t ${divider}`} />

        {/* Get App CTA */}
        <div className="px-3 py-4">
          <a
            href="#premium"
            className="flex items-center gap-3 rounded-lg px-4 py-3 font-bold bg-mellow-yellow text-black-grey"
            onClick={onClose}
          >
            <Play size={18} />
            Get the Mobile App
          </a>
        </div>

        <div className={`mx-3 border-t ${divider}`} />

        {/* Auth section */}
        <div className="px-3 py-4 mt-auto">
          {auth.isAuthenticated ? (
            <>
              {auth.email && (
                <p className={`px-4 pb-2 text-[0.76rem] font-bold uppercase tracking-[0.12em] ${metaText}`}>
                  {auth.email}
                </p>
              )}
              <button
                className={`${linkBase} w-full ${isDark ? 'text-[rgba(241,241,241,0.78)] hover:bg-[rgba(241,241,241,0.07)]' : 'text-[rgba(23,29,26,0.72)] hover:bg-[rgba(23,29,26,0.06)]'}`}
                onClick={() => { auth.signOut(); onClose(); }}
              >
                <LogOut size={18} />
                Sign Out
              </button>
            </>
          ) : (
            <button
              className={`${linkBase} w-full ${isDark ? 'text-[rgba(241,241,241,0.78)] hover:bg-[rgba(241,241,241,0.07)]' : 'text-[rgba(23,29,26,0.72)] hover:bg-[rgba(23,29,26,0.06)]'}`}
              onClick={() => { auth.openAuthPrompt('welcome'); onClose(); }}
            >
              <User size={18} />
              Sign In / Sign Up
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function AppHeader({ active }: { active?: 'feed' | 'admin' }) {
  const auth = useAuthSession();
  const [mounted, setMounted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const navLink = (href: string, label: string, key: 'feed') => (
    <a
      key={key}
      className={`rounded-lg px-[10px] py-[9px] ${active === key ? 'bg-[rgba(25,83,57,0.12)] text-dark-green' : 'text-[rgba(23,29,26,0.64)]'}`}
      href={href}
    >
      {label}
    </a>
  );

  const headerRight = (
    <div className="flex items-center gap-[10px]">
      <IconButton label="Notifications" variant="dark">
        <Bell size={18} />
      </IconButton>
      <a
        className="hidden sm:inline-flex border-0 rounded-lg items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow-yellow text-black-grey"
        href="#premium"
      >
        Get App
      </a>
      {/* Auth pill */}
      {mounted ? (
        auth.isAuthenticated ? (
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] px-3 h-[42px] text-[0.82rem] font-bold text-black-grey hover:bg-[rgba(23,29,26,0.1)]"
            type="button"
            onClick={() => setMenuOpen(true)}
            title={auth.email || 'Account'}
          >
            <User size={16} />
            <span className="hidden sm:inline max-w-[120px] truncate">
              {auth.email?.split('@')[0] ?? 'Account'}
            </span>
          </button>
        ) : (
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] px-3 h-[42px] text-[0.82rem] font-bold text-black-grey hover:bg-[rgba(23,29,26,0.1)]"
            type="button"
            onClick={() => auth.openAuthPrompt('welcome')}
          >
            <User size={16} />
            <span className="hidden sm:inline">Sign In</span>
          </button>
        )
      ) : (
        <div className="w-[42px] h-[42px] rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)]" />
      )}
      {/* Hamburger — mobile only */}
      <button
        className="sm:hidden w-[42px] h-[42px] rounded-lg inline-grid place-items-center border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] text-black-grey"
        type="button"
        onClick={() => setMenuOpen(true)}
        aria-label="Open menu"
      >
        <Menu size={19} />
      </button>
    </div>
  );

  return (
    <>
      <header className="sticky top-0 z-40 flex items-center justify-between gap-[18px] min-h-[72px] px-[clamp(16px,4vw,64px)] py-[14px] border-b border-[rgba(23,29,26,0.14)] bg-[rgba(241,241,241,0.92)] text-black-grey backdrop-blur-[18px]">
        <LogoMark />
        <nav className="flex items-center gap-[clamp(12px,2vw,26px)] text-[0.82rem] font-bold" aria-label="App navigation">
          {navLink('/feed', 'Event Feed', 'feed')}
        </nav>
        {headerRight}
      </header>
      {mounted && (
        <NavMenu
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          active={active}
          theme="light"
        />
      )}
    </>
  );
}

function IconButton({
  label,
  children,
  onClick,
  variant = 'ghost',
  disabled,
}: {
  label: string;
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'ghost' | 'dark' | 'yellow';
  disabled?: boolean;
}) {
  const base = 'w-[42px] h-[42px] rounded-lg inline-grid place-items-center border';
  const variants = {
    ghost: 'border-[rgba(241,241,241,0.17)] bg-[rgba(241,241,241,0.08)] text-aventi-white',
    dark: 'border-[rgba(241,241,241,0.17)] bg-[rgba(23,29,26,0.72)] text-aventi-white',
    yellow: 'border-[rgba(249,216,70,0.7)] bg-mellow-yellow text-black-grey',
  };
  return (
    <button
      className={`${base} ${variants[variant]}`}
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      title={label}
    >
      {children}
    </button>
  );
}

function MarketingHero() {
  const heroEvent = demoEvents[0];

  return (
    <section className="relative min-h-[min(92vh,920px)] overflow-hidden bg-black-grey text-aventi-white" id="top">
      <div className="absolute inset-0" aria-hidden="true">
        {heroImages.map((src, index) => (
          <img
            key={src}
            src={src}
            alt=""
            className="absolute inset-0 w-full h-full object-cover opacity-0 animate-[imageCycle_15s_infinite]"
            style={{ animationDelay: `${index * 5}s` }}
          />
        ))}
      </div>
      <div className={ds.heroOverlay} aria-hidden="true" />
      <div className={`relative z-[1] ${ds.wrap} px-[clamp(20px,4vw,72px)] pt-[clamp(56px,9vh,112px)] pb-[clamp(100px,14vh,140px)]`}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <span className="h-1 w-11 shrink-0 rounded-full bg-mellow-yellow shadow-[0_0_24px_rgba(249,216,70,0.45)]" aria-hidden="true" />
          <p className={`${ds.eyebrow} !tracking-[0.14em] text-aventi-white/95`}>Connected · Explorative · In flow</p>
        </div>
        <h1 className="mt-8 mb-6 font-semibold uppercase tracking-[0.06em] text-[clamp(3.25rem,14vw,9.5rem)] leading-[0.88] text-aventi-white drop-shadow-[0_4px_48px_rgba(0,0,0,0.35)]">
          Aventi
        </h1>
        <p className={`max-w-[34rem] m-0 text-[clamp(1.05rem,1.35vw,1.25rem)] ${ds.bodyOnDark}`}>
          The event discovery app for nights out and neighborhoods worth exploring. Set your vibe—then scroll real events
          that match your time, radius, budget, and mood.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-9">
          <a href="/feed" className={ds.btnPrimary}>
            <Play size={18} aria-hidden />
            Explore events
          </a>
          <a href="#how-it-works" className={ds.btnGhostOnDark}>
            <Sparkles size={18} aria-hidden />
            How it works
          </a>
        </div>
      </div>
      <div
        className={`absolute left-[clamp(16px,4vw,72px)] right-[clamp(16px,4vw,72px)] bottom-8 md:left-auto md:right-[clamp(20px,4vw,72px)] md:bottom-10 z-[2] w-auto md:w-[min(520px,42vw)] ${ds.statsStrip}`}
        aria-label="Live preview metrics"
      >
        <div className="grid grid-cols-1 divide-y divide-aventi-white/12 md:grid-cols-3 md:divide-x md:divide-y-0">
          <div className="p-5 md:p-[18px]">
            <span className="text-[0.72rem] font-bold uppercase tracking-[0.12em] text-aventi-white/48">Next up</span>
            <strong className="mt-2 block font-semibold text-[clamp(1.05rem,2vw,1.45rem)] leading-snug line-clamp-2">
              {heroEvent.title}
            </strong>
          </div>
          <div className="p-5 md:p-[18px]">
            <span className="text-[0.72rem] font-bold uppercase tracking-[0.12em] text-aventi-white/48">Market</span>
            <strong className="mt-2 block font-semibold text-[clamp(1.05rem,2vw,1.45rem)]">{heroEvent.city}</strong>
          </div>
          <div className="p-5 md:p-[18px]">
            <span className="text-[0.72rem] font-bold uppercase tracking-[0.12em] text-aventi-white/48">Signal</span>
            <strong className="mt-2 block font-semibold text-[clamp(1.05rem,2vw,1.45rem)] text-mellow-yellow/95">
              {vibeLabels[heroEvent.vibes[0]]}
            </strong>
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketingProductSection() {
  const [leadEvent, secondEvent] = demoEvents;

  return (
    <section className={`${ds.section} bg-aventi-white`} id="product">
      <div className={`${ds.wrap} grid gap-12 lg:gap-16 lg:grid-cols-[minmax(280px,1fr)_minmax(360px,1.15fr)] items-center`}>
        <div className="max-w-xl">
          <p className={ds.eyebrow}>Member product</p>
          <h2 className={`mt-4 mb-5 ${ds.h2}`}>Scroll until something feels worth leaving the house for.</h2>
          <p className={`${ds.bodyMuted} text-[1.05rem]`}>
            One event at a time—fast preference signals, rich detail when you need it, and a saved list for plans you
            actually want to make.
          </p>
          <div className="flex flex-wrap items-center gap-4 mt-9">
            <a className={ds.btnPrimary} href="/feed">
              <Compass size={18} aria-hidden />
              Open event feed
            </a>
            <a className={ds.linkAccent} href="#premium">
              See Premium
            </a>
          </div>
        </div>
        <div
          className="relative isolate min-h-[min(520px,70vw)] lg:min-h-[640px] rounded-aventi-panel border border-black-grey/10 overflow-hidden bg-[linear-gradient(135deg,rgba(25,83,57,0.92),rgba(58,144,106,0.74)),var(--color-dark-green)] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
          aria-label="Aventi feed preview"
        >
          <div className="absolute left-[clamp(14px,4vw,56px)] top-1/2 z-[1] w-[min(300px,calc(100%-28px))] -translate-y-1/2 border-[10px] border-device-bezel rounded-[34px] overflow-hidden bg-black-grey shadow-[0_28px_90px_rgba(0,0,0,0.38)]">
            <div className="flex justify-between px-4 pt-4 pb-3 text-aventi-white/65 text-[0.72rem] font-bold tracking-[0.14em] uppercase">
              <span>Aventi</span>
              <span>Tonight</span>
            </div>
            <div className="relative flex min-h-[440px] items-end sm:min-h-[480px]">
              <img src={leadEvent.imageUrl ?? heroImages[0]} alt="" className="absolute inset-0 h-full w-full object-cover" />
              <div className="absolute inset-0 bg-[linear-gradient(180deg,transparent_20%,rgba(23,29,26,0.92))]" />
              <div className="relative z-[1] px-4 pb-6 text-aventi-white">
                <span className="text-[0.72rem] font-bold tracking-[0.14em] uppercase text-mellow-yellow/95">
                  {categoryLabels[leadEvent.category]}
                </span>
                <h3 className="mt-2 mb-1 text-[clamp(1.5rem,4vw,2rem)] font-semibold uppercase tracking-[0.04em] leading-tight">
                  {leadEvent.title}
                </h3>
                <p className="m-0 text-aventi-white/72 text-[0.95rem]">
                  {leadEvent.venueName} · {formatPrice(leadEvent)}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 border-t border-aventi-white/10 bg-black-grey/40 p-3">
              {['Pass', 'Info', 'Save'].map((label) => (
                <span
                  key={label}
                  className="rounded-lg border border-aventi-white/14 py-2.5 text-center text-[0.72rem] font-bold uppercase tracking-wide text-aventi-white/75"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
          <div className={`absolute right-[clamp(12px,3vw,48px)] bottom-[clamp(16px,4vw,48px)] left-[clamp(12px,3vw,48px)] md:left-auto md:w-[min(380px,90%)] ${ds.card} p-6`}>
            <span className={`${ds.eyebrow} text-green`}>Next in queue</span>
            <h3 className="mt-3 mb-2 font-semibold text-black-grey text-[clamp(1.25rem,2.5vw,1.85rem)] leading-snug">
              {secondEvent.title}
            </h3>
            <p className={`${ds.bodyMuted} text-[0.98rem]`}>{secondEvent.description}</p>
            <div className="flex flex-wrap gap-2 mt-5">
              {secondEvent.vibes.slice(0, 3).map((vibe) => (
                <span
                  key={vibe}
                  className="rounded-lg border border-[rgba(25,83,57,0.2)] bg-[rgba(25,83,57,0.08)] px-3 py-1.5 text-[0.72rem] font-bold uppercase tracking-wide text-dark-green"
                >
                  {vibeLabels[vibe]}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketingFlowSection() {
  return (
    <section className={`${ds.section} bg-surface-mist`} id="how-it-works">
      <div className={ds.wrap}>
        <div className="mb-12 max-w-3xl">
          <p className={ds.eyebrow}>How it works</p>
          <h2 className={`mt-4 ${ds.h2}`}>A feed that learns your vibe, then opens up the city.</h2>
        </div>
        <div className="grid gap-5 md:grid-cols-3 md:gap-6">
          {[
            { num: '01', title: 'Set the night', body: 'Pick where you are, how far you will go, what you are into, and whether the evening is casual or big.' },
            { num: '02', title: 'Swipe with intent', body: 'Pass, save, share, or open details. Each signal teaches Aventi what should show up next.' },
            { num: '03', title: 'Build the plan', body: 'Save the standouts, get insider context, add tickets or maps, and keep a short list for the group chat.' },
          ].map((step) => (
            <article
              key={step.num}
              className={`${ds.cardMuted} flex min-h-[260px] flex-col p-8 shadow-[0_12px_40px_-20px_rgba(23,29,26,0.12)]`}
            >
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[rgba(58,144,106,0.18)] text-sm font-bold tabular-nums text-dark-green">
                {step.num}
              </span>
              <h3 className="mt-6 mb-3 font-semibold text-black-grey text-[clamp(1.2rem,2.2vw,1.65rem)] leading-snug">
                {step.title}
              </h3>
              <p className={`mt-auto ${ds.bodyMuted}`}>{step.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function MarketingVibeSection() {
  return (
    <section className={`${ds.section} bg-aventi-white`}>
      <div className={ds.wrap}>
        <div className="mb-12 max-w-3xl">
          <p className={ds.eyebrow}>Vibe check</p>
          <h2 className={`mt-4 mb-5 ${ds.h2}`}>Not another directory. A shortcut to your kind of night.</h2>
          <p className={`max-w-2xl text-[1.05rem] ${ds.bodyMuted}`}>
            Aventi starts with the signals people actually use when they make plans: location, radius, date, budget,
            energy level, and the scenes they want more of.
          </p>
        </div>
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 lg:gap-5"
          aria-label="Aventi vibe setup"
        >
          {[
            { icon: <MapPin size={22} strokeWidth={2} />, label: 'Where', value: 'Denver within 8 miles' },
            { icon: <CalendarDays size={22} strokeWidth={2} />, label: 'When', value: 'Tonight after 7' },
            { icon: <Sparkles size={22} strokeWidth={2} />, label: 'Vibe', value: 'Romantic, artsy, low-key' },
            { icon: <Filter size={22} strokeWidth={2} />, label: 'Budget', value: 'Free to moderate' },
          ].map((item) => (
            <article
              key={item.label}
              className={`${ds.card} flex min-h-[220px] flex-col justify-between p-7 bg-[linear-gradient(165deg,rgba(58,144,106,0.12),transparent_55%),rgba(255,255,255,0.85)]`}
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-aventi-panel bg-dark-green/10 text-green">{item.icon}</div>
              <div>
                <span className="block text-[0.72rem] font-bold uppercase tracking-[0.14em] text-black-grey/48">{item.label}</span>
                <strong className="mt-3 block font-semibold text-black-grey text-[clamp(1.05rem,2vw,1.35rem)] leading-snug">
                  {item.value}
                </strong>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function MarketingDetailsSection() {
  const event = demoEvents[2] ?? demoEvents[0];

  return (
    <section className={`${ds.section} bg-surface-sage`}>
      <div className={`${ds.wrap} grid gap-6 lg:grid-cols-[minmax(320px,1.35fr)_minmax(260px,0.65fr)] lg:items-stretch lg:gap-8`}>
        <div className={`${ds.card} grid overflow-hidden lg:grid-cols-[minmax(240px,0.9fr)_minmax(280px,1.1fr)]`}>
          <div className="relative min-h-[280px] lg:min-h-[520px]">
            <img src={event.imageUrl ?? heroImages[2]} alt="" className="absolute inset-0 h-full w-full object-cover" />
          </div>
          <div className="flex flex-col justify-center p-[clamp(24px,5vw,52px)]">
            <p className={ds.eyebrow}>Event details</p>
            <h2 className={`mt-5 mb-6 ${ds.h2}`}>Every card can become a plan.</h2>
            <p className={`${ds.bodyMuted} text-[1.05rem]`}>
              Open an event for the summary, vibe breakdown, date and distance, map context, shareable details, and the
              next move: tickets, calendar, directions, or something nearby to complete the night.
            </p>
            <div className="mt-8 flex flex-wrap gap-2.5" aria-label="Event detail actions">
              {[
                { icon: <Heart size={16} aria-hidden />, label: 'Save' },
                { icon: <Share2 size={16} aria-hidden />, label: 'Share' },
                { icon: <CalendarDays size={16} aria-hidden />, label: 'Calendar' },
                { icon: <MapPin size={16} aria-hidden />, label: 'Maps' },
              ].map((item) => (
                <span
                  key={item.label}
                  className="inline-flex min-h-[38px] items-center gap-2 rounded-lg border border-black-grey/12 bg-aventi-white/75 px-3 py-2 text-[0.76rem] font-bold uppercase tracking-wide text-dark-green"
                >
                  {item.icon}
                  {item.label}
                </span>
              ))}
            </div>
          </div>
        </div>
        <aside
          className={`${ds.card} flex flex-col justify-end bg-[linear-gradient(165deg,rgba(249,216,70,0.42),rgba(255,255,255,0.72)_48%),rgba(255,255,255,0.65)] p-[clamp(24px,4vw,40px)]`}
          aria-label="Premium insight preview"
        >
          <span className={`${ds.eyebrow} text-green`}>Premium insight</span>
          <h3 className="my-4 font-semibold text-black-grey text-[clamp(1.65rem,3.5vw,2.75rem)] leading-[1.05]">
            Why it matches
          </h3>
          <p className={`${ds.bodyMuted} text-[1.02rem]`}>
            Fits your artsy, after-work, under-$40 pattern. Pair it with a quiet dinner nearby and save the later jazz set
            as backup.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {['AI match', 'Insider tip', 'Complete the night'].map((tag) => (
              <span
                key={tag}
                className="inline-flex min-h-[36px] items-center rounded-lg border border-black-grey/12 bg-aventi-white/80 px-3 py-2 text-[0.76rem] font-bold uppercase tracking-wide text-dark-green"
              >
                {tag}
              </span>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}

function MarketingBeyondSection() {
  return (
    <section className={`${ds.section} bg-black-grey text-aventi-white`}>
      <div className={`${ds.wrap} grid gap-12 lg:grid-cols-[minmax(300px,1fr)_minmax(340px,1.05fr)] lg:items-center lg:gap-16`}>
        <div className="max-w-xl">
          <p className={ds.eyebrow}>Beyond discovery</p>
          <h2 className={`mt-5 mb-6 ${ds.h2OnDark}`}>From “what’s happening?” to “we’re going.”</h2>
          <p className="text-[1.05rem] leading-[1.75] text-aventi-white/58">
            Built for after discovery too: saved events, smarter calendars, friend-ready sharing, travel mode, and
            complete-the-night ideas that turn one good event into a real plan.
          </p>
          <a className={`mt-8 ${ds.btnGhostOnDark}`} href="/feed">
            <Compass size={18} aria-hidden />
            Try the feed
          </a>
        </div>
        <div
          className="rounded-aventi-panel border border-aventi-white/14 bg-[linear-gradient(145deg,rgba(58,144,106,0.22),transparent_50%),rgba(241,241,241,0.05)] p-6 shadow-[0_36px_100px_rgba(0,0,0,0.35)] backdrop-blur-md sm:p-8"
          aria-label="Aventi planning features"
        >
          {[
            { icon: <CalendarDays size={22} strokeWidth={2} />, label: 'Saved calendar', value: 'Keep the shortlist close' },
            { icon: <Share2 size={22} strokeWidth={2} />, label: 'Social planning', value: 'Share the exact event, not a search result' },
            { icon: <MapPin size={22} strokeWidth={2} />, label: 'Travel mode', value: 'Preview a city before you land' },
            { icon: <Sparkles size={22} strokeWidth={2} />, label: 'AI night builder', value: 'Dinner, show, after-hours—in one flow' },
          ].map((row, i) => (
            <div
              key={row.label}
              className={`grid grid-cols-[auto_1fr] gap-4 items-start py-6 ${i > 0 ? 'border-t border-aventi-white/12' : ''}`}
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-aventi-panel bg-mellow-yellow/12 text-mellow-yellow">
                {row.icon}
              </div>
              <div>
                <span className="mb-1.5 block text-[0.72rem] font-bold uppercase tracking-[0.14em] text-aventi-white/52">
                  {row.label}
                </span>
                <strong className="block font-semibold text-[clamp(1.05rem,2.2vw,1.45rem)] leading-snug text-aventi-white">
                  {row.value}
                </strong>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FilterRail({
  filters,
  onToggleCategory,
  onToggleVibe,
  onSetDate,
}: {
  filters: FeedFilters;
  onToggleCategory: (category: EventCategory) => void;
  onToggleVibe: (vibe: EventVibeTag) => void;
  onSetDate: (date: FeedFilters['date']) => void;
}) {
  const chipBase = 'border rounded-lg inline-flex items-center gap-[7px] min-h-[34px] px-[10px] text-[0.72rem] font-bold tracking-[0.16em] uppercase bg-transparent';
  const chipDefault = 'border-[rgba(23,29,26,0.14)] text-[rgba(23,29,26,0.72)]';
  const chipActive = 'border-green bg-[rgba(58,144,106,0.12)] text-dark-green';
  const chipYellow = 'border-[rgba(249,216,70,0.9)] bg-[rgba(249,216,70,0.35)]';
  const chipStrong = 'border-[rgba(23,29,26,0.14)] bg-black-grey text-aventi-white';

  return (
    <div className="flex flex-wrap gap-2 my-[18px]" aria-label="Feed filters">
      <button className={`${chipBase} ${chipStrong}`} type="button">
        <Filter size={15} />
        Filters
      </button>
      {(['today', 'tomorrow', 'weekend', 'week'] as const).map((date) => (
        <button
          key={date}
          className={`${chipBase} ${filters.date === date ? chipActive : chipDefault}`}
          type="button"
          onClick={() => onSetDate(date)}
        >
          {date === 'week' ? 'This Week' : date}
        </button>
      ))}
      {categoryOptions.map((category) => (
        <button
          key={category}
          className={`${chipBase} ${(filters.categories ?? []).includes(category) ? chipActive : chipDefault}`}
          type="button"
          onClick={() => onToggleCategory(category)}
        >
          {categoryLabels[category]}
        </button>
      ))}
      {vibeOptions.map((vibe) => (
        <button
          key={vibe}
          className={`${chipBase} ${(filters.vibes ?? []).includes(vibe) ? chipYellow : chipDefault}`}
          type="button"
          onClick={() => onToggleVibe(vibe)}
        >
          {vibeLabels[vibe]}
        </button>
      ))}
    </div>
  );
}

function EventPoster({
  event,
  action,
  onAction,
  onOpen,
}: {
  event: EventCard;
  action?: SwipeAction;
  onAction: (action: SwipeAction) => void;
  onOpen: () => void;
}) {
  return (
    <article
      className={`relative min-h-[min(720px,calc(100vh-130px))] mb-4 overflow-hidden rounded-lg scroll-snap-align-start bg-black-grey text-aventi-white ${action === 'like' ? 'outline outline-[3px] outline-[rgba(249,216,70,0.7)]' : ''}`}
    >
      <img src={event.imageUrl ?? heroImages[0]} alt="" className="object-cover absolute inset-0 w-full h-full" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(23,29,26,0.24),rgba(23,29,26,0.88)),linear-gradient(90deg,rgba(23,29,26,0.7),transparent_62%)]" />
      <div className="relative z-[1] flex justify-between gap-3 p-[18px]">
        <span className="border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(23,29,26,0.45)] backdrop-blur-[12px] px-[10px] py-2 text-[0.72rem] font-bold tracking-[0.16em] uppercase">{categoryLabels[event.category]}</span>
        <span className="border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(23,29,26,0.45)] backdrop-blur-[12px] px-[10px] py-2 text-[0.72rem] font-bold tracking-[0.16em] uppercase">{formatPrice(event)}</span>
      </div>
      <div className="absolute left-6 right-[108px] bottom-6 z-[1]">
        <div className="inline-flex items-center gap-2 border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(23,29,26,0.45)] backdrop-blur-[12px] px-[10px] py-2 text-[rgba(241,241,241,0.84)] text-[0.84rem] font-bold">
          <CalendarDays size={14} />
          {formatEventTime(event.startsAt)}
        </div>
        <h2 className="max-w-[760px] mt-[14px] mb-3 text-[clamp(2.25rem,6vw,5.7rem)] leading-[0.95] uppercase">{event.title}</h2>
        <p className="max-w-[580px] mb-4 text-[rgba(241,241,241,0.78)] leading-[1.65]">{event.description}</p>
        <div className="flex flex-wrap items-center gap-[14px] text-[rgba(241,241,241,0.78)] text-[0.92rem] font-semibold">
          <span className="inline-flex gap-2 items-center"><MapPin size={14} />{event.venueName}</span>
          <span className="inline-flex gap-2 items-center"><Compass size={14} />{event.radiusMiles?.toFixed(1)} mi</span>
        </div>
        <div className="flex flex-wrap gap-2 mt-[18px]">
          {event.vibes.slice(0, 4).map((vibe) => (
            <span key={vibe} className="border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(23,29,26,0.45)] backdrop-blur-[12px] px-[10px] py-[7px] text-[rgba(241,241,241,0.78)] text-[0.76rem] font-bold uppercase">{vibeLabels[vibe]}</span>
          ))}
        </div>
      </div>
      <div className="absolute right-[18px] bottom-6 z-[1] grid gap-[10px]">
        <IconButton label="Pass event" variant="dark" onClick={() => onAction('pass')}><X size={21} /></IconButton>
        <IconButton label="Event details" variant="dark" onClick={onOpen}><Info size={21} /></IconButton>
        <IconButton label="Share event" variant="dark"><Share2 size={20} /></IconButton>
        <IconButton label="Save event" variant="yellow" onClick={() => onAction('like')}>
          <Heart size={21} fill={action === 'like' ? 'currentColor' : 'none'} />
        </IconButton>
      </div>
    </article>
  );
}

export function EventFeedPage() {
  const auth = useAuthSession();
  const [events, setEvents] = useState<EventCard[]>(demoEvents);
  const [actions, setActions] = useState<Record<string, SwipeAction>>({});
  const [selectedEvent, setSelectedEvent] = useState<EventCard | null>(demoEvents[0] ?? null);
  const [isMining, setIsMining] = useState(false);
  const [filters, setFilters] = useState<FeedFilters>({
    date: 'week',
    price: 'any',
    radiusMiles: 25,
    vibes: [],
    categories: [],
  });

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      const categoryMatch = !filters.categories?.length || filters.categories.includes(event.category);
      const vibeMatch = !filters.vibes?.length || event.vibes.some((vibe) => filters.vibes?.includes(vibe));
      return categoryMatch && vibeMatch;
    });
  }, [events, filters.categories, filters.vibes]);

  function handleAction(event: EventCard, action: SwipeAction) {
    const result = applySwipeAction(events, actions, event.id, action);
    setActions(result.nextActions);
    setEvents(result.nextEvents);
    if (action === 'pass') {
      setSelectedEvent(result.nextEvents[0] ?? null);
    }
  }

  function toggleCategory(category: EventCategory) {
    setFilters((current) => ({
      ...current,
      categories: current.categories?.includes(category)
        ? current.categories.filter((item) => item !== category)
        : [...(current.categories ?? []), category],
    }));
  }

  function toggleVibe(vibe: EventVibeTag) {
    setFilters((current) => ({
      ...current,
      vibes: current.vibes?.includes(vibe)
        ? current.vibes.filter((item) => item !== vibe)
        : [...(current.vibes ?? []), vibe],
    }));
  }

  function refreshFeed() {
    setIsMining(true);
    window.setTimeout(() => {
      setEvents(demoEvents);
      setActions({});
      setSelectedEvent(demoEvents[0] ?? null);
      setIsMining(false);
    }, 900);
  }

  return (
    <>
      <AppHeader active="feed" />
      <section className="min-h-[calc(100vh-72px)] px-[clamp(16px,4vw,64px)] py-[clamp(62px,8vw,110px)]" id="feed">
        <div className="grid grid-cols-[280px_minmax(320px,1fr)_320px] gap-4 items-start">
          <aside className="sticky top-[84px] border border-[rgba(23,29,26,0.14)] rounded-lg bg-[rgba(255,255,255,0.48)] shadow-[0_24px_70px_rgba(23,29,26,0.2)] p-[18px]">
            <div className="mb-5"><LogoMark /></div>
            {auth.isAdmin ? (
              <a
                href="/admin"
                className="flex items-center gap-3 mb-5 min-h-[42px] px-3 border border-[rgba(23,29,26,0.14)] rounded-lg bg-[rgba(25,83,57,0.08)] text-[0.86rem] font-bold text-dark-green hover:bg-[rgba(25,83,57,0.12)] transition-colors"
              >
                <ShieldCheck size={18} aria-hidden />
                Admin Portal
              </a>
            ) : null}
            <div className="flex items-center gap-[10px] min-h-[42px] px-3 border border-[rgba(23,29,26,0.14)] rounded-lg bg-[rgba(241,241,241,0.72)] text-[0.86rem] font-semibold">
              <Search size={16} />
              <span>Denver, CO</span>
            </div>
            <FilterRail
              filters={filters}
              onToggleCategory={toggleCategory}
              onToggleVibe={toggleVibe}
              onSetDate={(date) => setFilters((current) => ({ ...current, date }))}
            />
            <div className="border border-[rgba(23,29,26,0.14)] rounded-lg p-4 bg-dark-green text-aventi-white">
              <div className="grid place-items-center w-[38px] h-[38px] mb-[14px] rounded-lg bg-[rgba(241,241,241,0.12)]">
                <Sparkles size={20} />
              </div>
              <strong className="block mb-[10px]">{isMining ? 'Mining new events' : 'Feed ready'}</strong>
              <p className="block mb-[10px] text-[rgba(241,241,241,0.58)]">
                {isMining
                  ? 'Queueing a fresh targeted city scan and refreshing visible inventory.'
                  : '184 visible events, Denver market warmed 6 minutes ago.'}
              </p>
              <button
                type="button"
                onClick={refreshFeed}
                className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow-yellow text-black-grey"
              >
                <RefreshCcw size={16} />
                Refresh
              </button>
            </div>
          </aside>
          <main className="h-[min(760px,calc(100vh-118px))] overflow-y-auto [scroll-snap-type:y_mandatory] pr-1" aria-label="Aventi event feed">
            {filteredEvents.length > 0 ? (
              filteredEvents.map((event) => (
                <EventPoster
                  key={event.id}
                  event={event}
                  action={actions[event.id]}
                  onAction={(action) => handleAction(event, action)}
                  onOpen={() => setSelectedEvent(event)}
                />
              ))
            ) : (
              <div className="grid place-items-center min-h-[300px] border border-dashed border-[rgba(23,29,26,0.14)] rounded-lg p-7 text-center">
                <Sparkles size={30} />
                <h3>No matches</h3>
                <p className="text-[rgba(23,29,26,0.58)]">Aventi would trigger a targeted warming scan for this filter signature.</p>
                <button
                  type="button"
                  onClick={refreshFeed}
                  className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow-yellow text-black-grey"
                >
                  Mine More Events
                </button>
              </div>
            )}
            <div className="flex items-center justify-center gap-2 min-h-[72px] mb-4 text-[rgba(23,29,26,0.54)] text-[0.78rem] font-extrabold uppercase">
              <ChevronDown size={18} />
              <span>Pull past the end to mine more events</span>
            </div>
          </main>
          <aside className="sticky top-[84px] border border-[rgba(23,29,26,0.14)] rounded-lg bg-[rgba(255,255,255,0.48)] shadow-[0_24px_70px_rgba(23,29,26,0.2)] p-[18px]">
            {selectedEvent ? (
              <>
                <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-green">Selected Event</span>
                <h3 className="mt-2 mb-3 text-[1.6rem] leading-[1.12]">{selectedEvent.title}</h3>
                <p className="leading-[1.65] text-[rgba(23,29,26,0.62)]">{selectedEvent.description}</p>
                <dl className="grid gap-3 my-[22px]">
                  {[
                    { label: 'Venue', value: selectedEvent.venueName },
                    { label: 'When', value: formatEventTime(selectedEvent.startsAt) },
                    { label: 'Signal', value: selectedEvent.vibes.map((vibe) => vibeLabels[vibe]).join(', ') },
                  ].map((item) => (
                    <div key={item.label}>
                      <dt className="text-[rgba(23,29,26,0.48)] text-[0.7rem] font-extrabold uppercase">{item.label}</dt>
                      <dd className="mt-1 font-semibold">{item.value}</dd>
                    </div>
                  ))}
                </dl>
                <button className="w-full border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow-yellow text-black-grey" type="button">
                  <CalendarDays size={17} />
                  Get Tickets
                </button>
              </>
            ) : (
              <div className="grid place-items-center min-h-[300px] border border-dashed border-[rgba(23,29,26,0.14)] rounded-lg p-7 text-center">
                <Eye size={26} />
                <p className="text-[rgba(23,29,26,0.58)]">Select an event to inspect details.</p>
              </div>
            )}
          </aside>
        </div>
      </section>
      <AuthModal />
    </>
  );
}

export function AdminPortalPage() {
  const auth = useAuthSession();
  const [activeTab, setActiveTab] = useState<'markets' | 'scans'>('markets');
  const [dashboard, setDashboard] = useState<AdminDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadDashboard(token?: string | null) {
    const t = token ?? auth.session?.access_token ?? null;
    if (!t) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await createAventiApi(t).getAdminDashboard();
      setDashboard(data);
    } catch (err) {
      setDashboard(null);
      setError(err instanceof Error ? err.message : 'Unable to load admin dashboard');
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (auth.isReady && auth.session) {
      void loadDashboard(auth.session.access_token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.isReady]);

  const tabBtn = (tab: 'markets' | 'scans') =>
    `border-0 rounded-[6px] inline-flex items-center gap-2 min-h-[38px] px-[14px] font-bold ${activeTab === tab ? 'bg-mellow-yellow text-black-grey' : 'bg-transparent text-aventi-white'}`;

  const authBox = 'border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(241,241,241,0.06)]';

  return (
    <>
      <AppHeader active="admin" />
      <section className="min-h-[calc(100vh-72px)] px-[clamp(16px,4vw,64px)] py-[clamp(62px,8vw,110px)] bg-black-grey text-aventi-white" id="admin">
        <div className="w-[min(800px,100%)] mb-[34px]">
          <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow-yellow">Admin portal</p>
          <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">Backend market scans, visible at a glance.</h2>
          <p className="max-w-[660px] text-[rgba(241,241,241,0.58)] leading-[1.75]">
            Operational views for heat tiers, inventory status, worker activity, ingest performance, and verification
            queues without making the product feel like a noisy control room.
          </p>
        </div>
        <div className="border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(241,241,241,0.06)] p-[18px]">
          <div className="flex items-center justify-between gap-4 mb-[18px]">
            <div>
              <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[rgba(241,241,241,0.55)]">Operations</span>
              <h3 className="mt-[6px] text-[clamp(1.4rem,3vw,2.5rem)]">Chron Market Scan Console</h3>
            </div>
            <div className="flex items-center gap-[6px] p-[5px] border border-[rgba(241,241,241,0.17)] rounded-lg" role="tablist" aria-label="Admin views">
              <button className={tabBtn('markets')} type="button" onClick={() => setActiveTab('markets')}>
                <Gauge size={16} />
                Markets
              </button>
              <button className={tabBtn('scans')} type="button" onClick={() => setActiveTab('scans')}>
                <Activity size={16} />
                Scans
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-[10px] mb-[18px] p-[10px] border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(241,241,241,0.06)]">
                <span className="mr-auto text-[rgba(241,241,241,0.78)] text-[0.86rem] font-bold">{auth.email ?? 'Admin session active'}</span>
                <button
                  type="button"
                  onClick={() => loadDashboard()}
                  disabled={isLoading}
                  className="border border-[rgba(241,241,241,0.17)] rounded-lg inline-flex items-center justify-center gap-2 min-h-[36px] px-[14px] bg-[rgba(241,241,241,0.08)] text-aventi-white font-extrabold disabled:opacity-55"
                >
                  <RefreshCcw size={15} />
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={() => auth.signOut()}
                  className="border border-[rgba(241,241,241,0.17)] rounded-lg inline-flex items-center justify-center gap-2 min-h-[36px] px-[14px] bg-[rgba(241,241,241,0.08)] text-aventi-white font-extrabold"
                >
                  <LogOut size={15} />
                  Sign Out
                </button>
          </div>
          {error ? (
                <div className={`grid gap-3 place-items-center p-7 min-h-0 text-center ${authBox} mb-[18px]`}>
                  <Lock size={24} />
                  <h3 className="m-0 text-[clamp(1.2rem,2vw,1.8rem)]">Admin access blocked</h3>
                  <p className="max-w-[560px] m-0 text-[rgba(241,241,241,0.58)] leading-[1.65]">
                    {error.includes('403') ? 'This Supabase user is signed in, but the backend rejected the admin role claim.' : error}
                  </p>
                </div>
          ) : null}
          {isLoading && !dashboard ? (
                <div className={`grid gap-3 place-items-center p-7 min-h-0 text-center ${authBox} mb-[18px]`}>
                  <Loader2 size={24} className="animate-spin" />
                  <h3 className="m-0 text-[clamp(1.2rem,2vw,1.8rem)]">Loading scan telemetry</h3>
                  <p className="max-w-[560px] m-0 text-[rgba(241,241,241,0.58)] leading-[1.65]">Reading market inventory state, ingest runs, and verification health from the backend.</p>
                </div>
          ) : dashboard ? (
            <>
                  <div className="grid grid-cols-4 gap-[10px] mb-[18px]">
                    {[
                      { label: 'Markets', value: dashboard.rollup.marketsTotal },
                      { label: 'Hot Markets', value: dashboard.rollup.hotMarkets },
                      { label: 'Active Scans', value: dashboard.rollup.activeScans },
                      { label: 'Verification Backlog', value: dashboard.rollup.verificationBacklog },
                    ].map((metric) => (
                      <div key={metric.label} className="border border-[rgba(241,241,241,0.17)] rounded-lg p-[18px] bg-[rgba(241,241,241,0.05)]">
                        <span className="text-[rgba(241,241,241,0.58)] text-[0.72rem] font-extrabold uppercase">{metric.label}</span>
                        <strong className="block mt-2 text-[clamp(1.6rem,4vw,3rem)] leading-[1]">{metric.value}</strong>
                      </div>
                    ))}
                  </div>
                  {activeTab === 'markets' ? (
                    <div className="border border-[rgba(241,241,241,0.17)] rounded-lg overflow-x-auto" role="table" aria-label="Market inventory state">
                      <div className="grid grid-cols-[1.3fr_1fr_0.7fr_1fr_1.1fr_0.7fr] gap-4 min-w-[860px] px-4 py-[15px] items-center text-[rgba(241,241,241,0.55)] text-[0.72rem] font-extrabold uppercase" role="row">
                        <span>Market</span><span>Status</span><span>Visible</span><span>Last Scan</span><span>Targeted</span><span>Active Users</span>
                      </div>
                      {dashboard.markets.map((market) => {
                        const status = marketStatus(market);
                        const statusColor =
                          status === 'ready' ? 'bg-[rgba(58,144,106,0.32)] text-aventi-white' :
                          status === 'warming' || status === 'targeted_warming' ? 'bg-[rgba(249,216,70,0.2)] text-mellow-yellow' :
                          'bg-[rgba(241,241,241,0.1)] text-aventi-white';
                        return (
                          <div className="grid grid-cols-[1.3fr_1fr_0.7fr_1fr_1.1fr_0.7fr] gap-4 min-w-[860px] px-4 py-[15px] items-center border-t border-[rgba(241,241,241,0.12)]" role="row" key={market.marketKey}>
                            <span>
                              <strong className="block">{market.city}</strong>
                              <small className="block mt-1 text-[rgba(241,241,241,0.58)]">{market.heatTier} - {market.state ?? market.country}</small>
                            </span>
                            <span className={`w-fit px-[9px] py-[6px] rounded-lg border border-[rgba(241,241,241,0.17)] text-[0.72rem] font-extrabold uppercase capitalize ${statusColor}`}>{status.replace('_', ' ')}</span>
                            <span>{market.visibleEventCount7d}</span>
                            <span>{formatDateTime(market.lastScanCompletedAt ?? market.lastScanStartedAt)}</span>
                            <span>{formatDateTime(market.lastTargetedRequestedAt)}</span>
                            <span>{market.activeUserCount7d}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="grid gap-[10px]">
                      {dashboard.ingestRuns.map((run) => {
                        const runColor =
                          run.status === 'succeeded' ? 'bg-[rgba(58,144,106,0.32)] text-aventi-white' :
                          run.status === 'running' || run.status === 'queued' || run.status === 'completed' ? 'bg-[rgba(249,216,70,0.2)] text-mellow-yellow' :
                          'bg-[rgba(241,241,241,0.1)] text-aventi-white';
                        return (
                          <article className="grid grid-cols-[minmax(220px,1fr)_minmax(280px,1.3fr)_auto] gap-4 items-center p-4 border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(241,241,241,0.06)]" key={run.id}>
                            <div>
                              <span className="text-mellow-yellow text-[0.76rem] font-extrabold uppercase">{run.id.slice(0, 12)}</span>
                              <h4 className="my-[5px] text-[1.04rem]">{run.city ?? 'Unknown market'} - {run.sourceType ?? 'source'}</h4>
                              <p className="text-[rgba(241,241,241,0.58)]">{run.sourceName ?? 'ingest'} started {formatDateTime(run.startedAt)}</p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {[`${run.discoveredCount} found`, `${run.insertedCount} inserted`, formatDateTime(run.finishedAt), run.errorMessage ? 'error' : 'clean'].map((s) => (
                                <span key={s} className="rounded-lg px-[9px] py-[7px] bg-[rgba(241,241,241,0.08)] text-[0.74rem] font-extrabold uppercase">{s}</span>
                              ))}
                            </div>
                            <strong className={`rounded-lg px-[9px] py-[7px] text-[0.74rem] font-extrabold uppercase ${runColor}`}>{run.status}</strong>
                          </article>
                        );
                      })}
                      <article className="grid grid-cols-[minmax(220px,1fr)_minmax(280px,1.3fr)_auto] gap-4 items-center p-4 border border-[rgba(241,241,241,0.17)] rounded-lg bg-[rgba(241,241,241,0.06)]">
                        <div>
                          <span className="text-mellow-yellow text-[0.76rem] font-extrabold uppercase">verification</span>
                          <h4 className="my-[5px] text-[1.04rem]">Verification health</h4>
                          <p className="text-[rgba(241,241,241,0.58)]">{dashboard.workerQueue.configured ? 'Worker queue configured' : 'Worker queue not configured'}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {dashboard.verification.slice(0, 4).map((item) => (
                            <span key={`${item.status}-${String(item.active)}`} className="rounded-lg px-[9px] py-[7px] bg-[rgba(241,241,241,0.08)] text-[0.74rem] font-extrabold uppercase">
                              {item.status}: {item.count}
                            </span>
                          ))}
                        </div>
                        <strong className="rounded-lg px-[9px] py-[7px] bg-[rgba(58,144,106,0.32)] text-[0.74rem] font-extrabold uppercase">{dashboard.workerQueue.pollSeconds}s poll</strong>
                      </article>
                    </div>
                  )}
            </>
          ) : null}
        </div>
      </section>
      <AuthModal />
    </>
  );
}

function PricingSection() {
  return (
    <section className={`${ds.section} bg-surface-mist`} id="premium">
      <div className={ds.wrap}>
        <div className="mb-12 max-w-3xl">
          <p className={ds.eyebrow}>Aventi Premium</p>
          <h2 className={`mt-4 ${ds.h2}`}>Start free. Upgrade when you want the whole city.</h2>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:gap-8">
          {[
            {
              icon: <User size={24} strokeWidth={2} className="text-dark-green" />,
              title: 'Free Discovery',
              desc: 'Browse local events, save favorites, share plans, and teach the feed what kind of nights you want more of.',
              features: ['Daily discovery feed', 'Saved events and favorites', 'Basic vibe and distance filters'],
              cta: 'Launch Aventi',
              featured: false,
            },
            {
              icon: <ShieldCheck size={24} strokeWidth={2} className="text-dark-green" />,
              title: 'Premium',
              desc: 'Unlock deeper search, trip planning, and AI context for people who want Aventi to become their city guide.',
              features: ['Unlimited swipes', 'Travel mode and advanced filters', 'Insider tips and complete-the-night ideas'],
              cta: 'Explore Premium',
              featured: true,
            },
          ].map((plan) => (
            <article
              key={plan.title}
              className={`${ds.card} flex flex-col p-8 transition-shadow hover:shadow-[0_28px_80px_-18px_rgba(23,29,26,0.22)] ${
                plan.featured ? 'ring-2 ring-dark-green/25 ring-offset-2 ring-offset-surface-mist' : ''
              }`}
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-aventi-panel bg-[rgba(25,83,57,0.1)]">{plan.icon}</div>
              <h3 className="mt-6 mb-3 font-semibold text-black-grey text-[clamp(1.35rem,2.8vw,2rem)]">{plan.title}</h3>
              <p className={`${ds.bodyMuted} flex-1 text-[1.02rem]`}>{plan.desc}</p>
              <ul className="mt-6 grid list-none gap-3 p-0">
                {plan.features.map((f) => (
                  <li key={f} className="relative pl-6 text-[0.98rem] leading-relaxed text-black-grey/68 before:absolute before:left-0 before:top-[0.5em] before:h-2 before:w-2 before:rounded-full before:bg-green before:content-['']">
                    {f}
                  </li>
                ))}
              </ul>
              <a className={`mt-8 w-full sm:w-auto ${ds.btnPrimary}`} href="/feed">
                {plan.cta}
              </a>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export function MarketingHome() {
  return (
    <>
      <AppHeader />
      <MarketingHero />
      <MarketingProductSection />
      <MarketingFlowSection />
      <MarketingVibeSection />
      <MarketingDetailsSection />
      <MarketingBeyondSection />
      <PricingSection />
      <footer className="border-t border-black-grey/12 bg-aventi-white">
        <div className={`${ds.wrap} flex flex-col gap-8 py-12 sm:flex-row sm:items-center sm:justify-between`}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-10">
            <LogoMark />
            <nav className="flex flex-wrap gap-x-6 gap-y-2 text-[0.82rem] font-semibold text-black-grey/55">
              <a className="transition-colors hover:text-dark-green" href="#product">
                Product
              </a>
              <a className="transition-colors hover:text-dark-green" href="#how-it-works">
                How it works
              </a>
              <a className="transition-colors hover:text-dark-green" href="#premium">
                Premium
              </a>
              <a className="transition-colors hover:text-dark-green" href="/feed">
                Feed
              </a>
            </nav>
          </div>
          <p className="max-w-md text-[0.78rem] font-medium uppercase tracking-[0.12em] text-black-grey/45 leading-relaxed">
            Poppins · matte neutrals · generous space — Aventi brand system.
          </p>
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-aventi-panel border border-green/30 bg-green/10 text-green">
            <Check size={18} strokeWidth={2.5} aria-hidden />
          </div>
        </div>
      </footer>
      <button
        className="fixed right-[18px] bottom-[18px] z-30 flex h-12 w-12 items-center justify-center rounded-aventi-panel border border-dark-green/20 bg-mellow-yellow text-black-grey shadow-[0_16px_48px_-8px_rgba(23,29,26,0.35)] transition-transform hover:scale-[1.03] active:scale-[0.98]"
        type="button"
        aria-label="Scroll down"
        onClick={() => window.scrollBy({ top: window.innerHeight, behavior: 'smooth' })}
      >
        <ArrowDown size={20} strokeWidth={2.5} aria-hidden />
      </button>
      <AuthModal />
    </>
  );
}
