'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import type { Session } from '@supabase/supabase-js';
import {
  Activity,
  ArrowDown,
  Bell,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Compass,
  Dumbbell,
  Eye,
  Filter,
  Gauge,
  Heart,
  Home,
  Info,
  Leaf,
  Loader2,
  Lock,
  LogOut,
  MapPin,
  Menu,
  Mountain,
  Music2,
  Palette,
  PartyPopper,
  Pencil,
  Play,
  RefreshCcw,
  Search,
  Settings,
  Share2,
  ShieldCheck,
  Smartphone,
  SlidersHorizontal,
  Store,
  Theater,
  Sparkles,
  User,
  UtensilsCrossed,
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
  categoryTopTags,
  demoEvents,
  heroImages,
  vibeLabels,
} from '@/lib/demo-data';
import { createAventiApi } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import { useAuthSession } from '@/lib/auth-session';
import { AuthModal } from './AuthModal';
import { Button, ButtonLink, Pill, Surface, glass, motion, type } from './ui/app-ui';
import { AppShell } from './ui/app-shell';

const categoryOptions: EventCategory[] = [
  'nightlife',
  'dining',
  'concerts',
  'comedy',
  'experiences',
  'markets',
  'wellness',
  'sports',
  'outdoors',
  'tech',
];
const vibeOptions: EventVibeTag[] = [
  'chill',
  'energetic',
  'social',
  'romantic',
  'intimate',
  'solo-friendly',
  'family',
  'adventurous',
  'underground',
  'late-night',
  'live-music',
  'intellectual',
  'wellness',
  'luxury',
];

const categoryIcons: Record<EventCategory, React.ReactNode> = {
  nightlife: <PartyPopper size={18} />,
  dining: <UtensilsCrossed size={18} />,
  concerts: <Music2 size={18} />,
  wellness: <Leaf size={18} />,
  experiences: <Palette size={18} />,
  comedy: <Theater size={18} />,
  sports: <Dumbbell size={18} />,
  outdoors: <Mountain size={18} />,
  markets: <Store size={18} />,
  tech: <Code2 size={18} />,
};

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
  active?: 'home' | 'feed' | 'admin' | 'profile';
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
    ? 'bg-[#171d1a] text-[#f1f1f1] border-[rgba(241,241,241,0.12)]'
    : 'bg-[#f1f1f1] text-[#171d1a] border-[rgba(23,29,26,0.12)]';
  const divider = isDark ? 'border-[rgba(241,241,241,0.1)]' : 'border-[rgba(23,29,26,0.1)]';
  const linkBase = 'flex items-center gap-3 rounded-lg px-4 py-3 text-[1rem] font-bold transition-colors';
  const linkActive = isDark
    ? 'bg-[rgba(249,216,70,0.12)] text-[#f9d846]'
    : 'bg-[rgba(25,83,57,0.1)] text-[#195339]';
  const linkIdle = isDark
    ? 'text-[rgba(241,241,241,0.78)] hover:bg-[rgba(241,241,241,0.07)]'
    : 'text-[rgba(23,29,26,0.72)] hover:bg-[rgba(23,29,26,0.06)]';
  const metaText = isDark ? 'text-[rgba(241,241,241,0.44)]' : 'text-[rgba(23,29,26,0.44)]';

  const navItems: { href: string; label: string; icon: React.ReactNode; key: string }[] = [
    { href: '/',       label: 'Home',         icon: <Compass size={18} />,     key: 'home' },
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
            href="#get-app"
            className="flex items-center gap-3 rounded-lg px-4 py-3 font-bold bg-[#f9d846] text-[#171d1a]"
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

function AppHeader({ active }: { active: 'home' | 'feed' | 'admin' | 'profile' }) {
  const auth = useAuthSession();
  const [mounted, setMounted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const navLink = (href: string, label: string, key: 'home' | 'feed' | 'admin') => (
    <a
      key={key}
      className={`rounded-lg px-[10px] py-[9px] ${active === key ? 'bg-[rgba(25,83,57,0.12)] text-[#195339]' : 'text-[rgba(23,29,26,0.64)]'}`}
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
        className="hidden sm:inline-flex border-0 rounded-lg items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[#f9d846] text-[#171d1a]"
        href="#get-app"
      >
        Get App
      </a>
      {/* Auth pill */}
      {mounted ? (
        auth.isAuthenticated ? (
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] px-3 h-[42px] text-[0.82rem] font-bold text-[#171d1a] hover:bg-[rgba(23,29,26,0.1)]"
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
            className="inline-flex items-center gap-2 rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] px-3 h-[42px] text-[0.82rem] font-bold text-[#171d1a] hover:bg-[rgba(23,29,26,0.1)]"
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
        className="sm:hidden w-[42px] h-[42px] rounded-lg inline-grid place-items-center border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] text-[#171d1a]"
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
      <header className="sticky top-0 z-40 flex items-center justify-between gap-[18px] min-h-[72px] px-[clamp(16px,4vw,64px)] py-[14px] border-b border-[rgba(23,29,26,0.14)] bg-[rgba(241,241,241,0.92)] text-[#171d1a] backdrop-blur-[18px]">
        <LogoMark />
        <nav className="flex items-center gap-[clamp(12px,2vw,26px)] text-[0.82rem] font-bold" aria-label="App navigation">
          {navLink('/', 'Home', 'home')}
          {navLink('/feed', 'Event Feed', 'feed')}
          {mounted && auth.isAdmin && navLink('/admin', 'Admin Portal', 'admin')}
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
    ghost: 'border-[rgba(241,241,241,0.17)] bg-[rgba(241,241,241,0.08)] text-[#f1f1f1]',
    dark: 'border-[rgba(241,241,241,0.17)] bg-[rgba(23,29,26,0.72)] text-[#f1f1f1]',
    yellow: 'border-[rgba(249,216,70,0.7)] bg-[#f9d846] text-[#171d1a]',
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
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
    <section className="relative min-h-[92vh] overflow-hidden bg-[#171d1a] text-[#f1f1f1]" id="top">
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
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(23,29,26,0.92),rgba(23,29,26,0.58)_52%,rgba(23,29,26,0.2)),linear-gradient(0deg,rgba(23,29,26,0.65),transparent_42%)]" />
      <header className="relative z-[2] flex items-center justify-between gap-6 px-[clamp(20px,4vw,64px)] py-7">
        <LogoMark />
        <nav className="flex items-center gap-[clamp(16px,2.5vw,34px)] text-[rgba(241,241,241,0.74)] text-[0.82rem] font-semibold" aria-label="Primary">
          <a href="#product">Product</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#premium">Premium</a>
          <a href="/feed">Event Feed</a>
        </nav>
        <div className="flex items-center gap-[10px]">
          <IconButton label="Notifications">
            <Bell size={18} />
          </IconButton>
          <a className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[#f9d846] text-[#171d1a]" href="/feed">
            Open App
          </a>
          <div className="sm:hidden">
            <IconButton label="Menu" onClick={() => setMenuOpen(true)}>
              <Menu size={19} />
            </IconButton>
          </div>
        </div>
      </header>
      <div className="relative z-[1] w-[min(760px,calc(100%-40px))] px-[clamp(20px,4vw,64px)] pt-[clamp(70px,11vh,132px)] pb-[110px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">Connected. Explorative. In flow.</p>
        <h1 className="mt-[10px] mb-[18px] text-[clamp(4.5rem,16vw,12rem)] leading-[0.86] uppercase">Aventi</h1>
        <p className="max-w-[650px] m-0 text-[rgba(241,241,241,0.78)] text-[clamp(1.02rem,1.4vw,1.3rem)] leading-[1.7]">
          A vertical event discovery app for nights out, new neighborhoods, and plans that should feel easy to say yes
          to. Tell Aventi your vibe, then scroll real events that fit your time, radius, budget, and mood.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-[30px]">
          <a href="/feed" className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[#f9d846] text-[#171d1a]">
            <Play size={18} />
            Explore Events
          </a>
          <a href="#how-it-works" className="border border-[rgba(241,241,241,0.17)] rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[rgba(241,241,241,0.08)] text-[#f1f1f1]">
            <Sparkles size={18} />
            How It Works
          </a>
        </div>
      </div>
      <div
        className="absolute right-[clamp(20px,4vw,64px)] bottom-7 z-[2] grid grid-cols-3 w-[min(520px,calc(100%-40px))] border border-[rgba(241,241,241,0.17)] bg-[rgba(23,29,26,0.72)] backdrop-blur-[18px]"
        aria-label="Live operating metrics"
      >
        <div className="p-[18px]">
          <span className="text-[rgba(241,241,241,0.58)]">Next Up</span>
          <strong className="block mt-[6px] text-[1.55rem]">{heroEvent.title}</strong>
        </div>
        <div className="p-[18px]">
          <span className="text-[rgba(241,241,241,0.58)]">Market</span>
          <strong className="block mt-[6px] text-[1.55rem]">{heroEvent.city}</strong>
        </div>
        <div className="p-[18px]">
          <span className="text-[rgba(241,241,241,0.58)]">Signal</span>
          <strong className="block mt-[6px] text-[1.55rem]">{vibeLabels[heroEvent.vibes[0]]}</strong>
        </div>
      </div>
    </section>
    <NavMenu open={menuOpen} onClose={() => setMenuOpen(false)} theme="dark" />
    </>
  );
}

function MarketingProductSection() {
  const [leadEvent, secondEvent] = demoEvents;

  return (
    <section className="grid grid-cols-[minmax(280px,0.82fr)_minmax(360px,1.18fr)] gap-[clamp(28px,5vw,72px)] items-center px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-[#f1f1f1]" id="product">
      <div>
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">Member product</p>
        <h2 className="max-w-[760px] mt-[10px] mb-[18px] text-[clamp(2.5rem,7vw,6.3rem)] leading-[0.96]">Scroll until something feels worth leaving the house for.</h2>
        <p className="text-[rgba(23,29,26,0.62)] leading-[1.75]">
          Aventi brings the mobile feed to web without losing the core interaction: one event at a time, fast preference
          signals, useful details close at hand, and a saved list for plans you actually want to make.
        </p>
        <div className="flex flex-wrap items-center gap-[18px] mt-[28px]">
          <a className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[#f9d846] text-[#171d1a]" href="/feed">
            <Compass size={18} />
            Open Event Feed
          </a>
          <a className="border-b-2 border-[rgba(25,83,57,0.28)] text-[#195339] font-extrabold" href="#premium">
            See Premium
          </a>
        </div>
      </div>
      <div className="relative min-h-[680px] border border-[rgba(23,29,26,0.12)] rounded-lg overflow-hidden bg-[linear-gradient(135deg,rgba(25,83,57,0.92),rgba(58,144,106,0.74)),#195339]" aria-label="Aventi feed preview">
        <div className="absolute left-[clamp(18px,5vw,70px)] top-1/2 -translate-y-1/2 w-[min(330px,calc(100%-36px))] border-[10px] border-[#111611] rounded-[34px] overflow-hidden bg-[#171d1a] shadow-[0_30px_80px_rgba(0,0,0,0.32)]">
          <div className="flex justify-between px-[18px] pt-[18px] pb-3 text-[rgba(241,241,241,0.68)] text-[0.72rem] font-extrabold tracking-[0.12em] uppercase">
            <span>Aventi</span>
            <span>Tonight</span>
          </div>
          <div className="relative min-h-[480px] flex items-end">
            <img src={leadEvent.imageUrl ?? heroImages[0]} alt="" className="object-cover absolute inset-0 w-full h-full" />
            <div className="absolute inset-0 bg-[linear-gradient(180deg,transparent,rgba(23,29,26,0.88))]" />
            <div className="relative z-[1] px-[18px] pb-[22px] text-[#f1f1f1]">
              <span className="text-[0.72rem] font-extrabold tracking-[0.12em] uppercase">{categoryLabels[leadEvent.category]}</span>
              <h3 className="my-2 text-[2.1rem] leading-[0.98] uppercase">{leadEvent.title}</h3>
              <p className="m-0 text-[rgba(241,241,241,0.72)]">
                {leadEvent.venueName} · {formatPrice(leadEvent)}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 p-3">
            {['Pass', 'Info', 'Save'].map((label) => (
              <span key={label} className="border border-[rgba(241,241,241,0.16)] rounded-lg py-[10px] px-1 text-[rgba(241,241,241,0.7)] text-center text-[0.75rem] font-extrabold uppercase">
                {label}
              </span>
            ))}
          </div>
        </div>
        <div className="absolute right-[clamp(18px,5vw,70px)] bottom-[clamp(20px,6vw,76px)] w-[min(380px,calc(100%-36px))] border border-[rgba(241,241,241,0.2)] rounded-lg p-[22px] bg-[rgba(241,241,241,0.9)] shadow-[0_22px_70px_rgba(0,0,0,0.22)]">
          <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#3a906a]">Next in queue</span>
          <h3 className="mt-[9px] mb-[10px] text-[clamp(1.35rem,3vw,2.3rem)] leading-[1.05]">{secondEvent.title}</h3>
          <p className="text-[rgba(23,29,26,0.62)] leading-[1.75]">{secondEvent.description}</p>
          <div className="flex flex-wrap gap-2 mt-[18px]">
            {secondEvent.vibes.slice(0, 3).map((vibe) => (
              <span key={vibe} className="border border-[rgba(23,29,26,0.12)] rounded-lg px-[10px] py-[7px] bg-[rgba(25,83,57,0.08)] text-[#195339] text-[0.76rem] font-bold uppercase">{vibeLabels[vibe]}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketingFlowSection() {
  return (
    <section className="px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-[#e7ece6]" id="how-it-works">
      <div className="w-[min(800px,100%)] mb-[34px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">How it works</p>
        <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">A feed that learns your vibe, then opens up the city.</h2>
      </div>
      <div className="grid grid-cols-3 border-t border-[rgba(23,29,26,0.16)]">
        {[
          { num: '01', title: 'Set the night', body: 'Pick where you are, how far you will go, what you are into, and whether the evening is casual or big.' },
          { num: '02', title: 'Swipe with intent', body: 'Pass, save, share, or open details. Each signal teaches Aventi what should show up next.' },
          { num: '03', title: 'Build the plan', body: 'Save the standouts, get insider context, add tickets or maps, and keep a short list for the group chat.' },
        ].map((step, i) => (
          <article key={step.num} className={`min-h-[280px] p-[clamp(22px,3vw,38px)] ${i < 2 ? 'border-r border-[rgba(23,29,26,0.16)]' : ''}`}>
            <span className="text-[0.72rem] font-extrabold tracking-[0.12em] uppercase text-[#3a906a]">{step.num}</span>
            <h3 className="mt-6 mb-[10px] text-[clamp(1.4rem,3vw,2.6rem)] leading-[1.04]">{step.title}</h3>
            <p className="text-[rgba(23,29,26,0.62)] leading-[1.75]">{step.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function MarketingVibeSection() {
  return (
    <section className="px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-[#f1f1f1]">
      <div className="w-[min(800px,100%)] mb-[34px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">Vibe check</p>
        <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">Not another directory. A shortcut to your kind of night.</h2>
        <p className="max-w-[660px] text-[rgba(23,29,26,0.62)] leading-[1.75]">
          Aventi starts with the signals people actually use when they make plans: location, radius, date, budget,
          energy level, and the scenes they want more of.
        </p>
      </div>
      <div className="grid grid-cols-4 gap-[14px]" aria-label="Aventi vibe setup">
        {[
          { icon: <MapPin size={22} />, label: 'Where', value: 'Denver within 8 miles' },
          { icon: <CalendarDays size={22} />, label: 'When', value: 'Tonight after 7' },
          { icon: <Sparkles size={22} />, label: 'Vibe', value: 'Romantic, artsy, low-key' },
          { icon: <Filter size={22} />, label: 'Budget', value: 'Free to moderate' },
        ].map((item) => (
          <article key={item.label} className="min-h-[230px] border border-[rgba(23,29,26,0.12)] rounded-lg p-[clamp(20px,2.5vw,30px)] flex flex-col justify-between bg-[linear-gradient(180deg,rgba(58,144,106,0.08),transparent),rgba(255,255,255,0.72)]">
            <div className="text-[#3a906a]">{item.icon}</div>
            <div>
              <span className="block text-[rgba(23,29,26,0.5)] text-[0.72rem] font-extrabold tracking-[0.12em] uppercase">{item.label}</span>
              <strong className="block mt-[10px] text-[#171d1a] text-[clamp(1.15rem,2.5vw,2rem)] leading-[1.08]">{item.value}</strong>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function MarketingDetailsSection() {
  const event = demoEvents[2] ?? demoEvents[0];

  return (
    <section className="grid grid-cols-[minmax(420px,1.35fr)_minmax(280px,0.65fr)] gap-4 items-stretch px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-[#dfe8dd]">
      <div className="border border-[rgba(23,29,26,0.12)] rounded-lg bg-[rgba(255,255,255,0.52)] shadow-[0_24px_70px_rgba(23,29,26,0.2)] grid grid-cols-[minmax(260px,0.85fr)_minmax(320px,1.15fr)] overflow-hidden">
        <img src={event.imageUrl ?? heroImages[2]} alt="" className="w-full h-full min-h-[520px] object-cover" />
        <div className="p-[clamp(26px,5vw,58px)] flex flex-col justify-center">
          <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">Event details</p>
          <h2 className="mt-[10px] mb-[18px] text-[clamp(2.4rem,6vw,5.6rem)] leading-[0.96]">Every card can become a plan.</h2>
          <p className="text-[rgba(23,29,26,0.62)] leading-[1.75]">
            Open an event for the summary, vibe breakdown, date and distance, map context, shareable details, and the
            next move: tickets, calendar, directions, or something nearby to complete the night.
          </p>
          <div className="flex flex-wrap gap-[10px] mt-[26px]" aria-label="Event detail actions">
            {[
              { icon: <Heart size={16} />, label: 'Save' },
              { icon: <Share2 size={16} />, label: 'Share' },
              { icon: <CalendarDays size={16} />, label: 'Calendar' },
              { icon: <MapPin size={16} />, label: 'Maps' },
            ].map((item) => (
              <span key={item.label} className="min-h-[38px] border border-[rgba(23,29,26,0.12)] rounded-lg px-[10px] py-2 inline-flex items-center gap-2 bg-[rgba(255,255,255,0.58)] text-[#195339] text-[0.78rem] font-extrabold uppercase">
                {item.icon}
                {item.label}
              </span>
            ))}
          </div>
        </div>
      </div>
      <aside
        className="border border-[rgba(23,29,26,0.12)] rounded-lg shadow-[0_24px_70px_rgba(23,29,26,0.2)] p-[clamp(24px,4vw,38px)] flex flex-col justify-end bg-[linear-gradient(180deg,rgba(249,216,70,0.34),rgba(255,255,255,0.54)),rgba(255,255,255,0.54)]"
        aria-label="Premium insight preview"
      >
        <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#3a906a]">Premium insight</span>
        <h3 className="my-3 text-[clamp(1.8rem,4vw,3.7rem)] leading-[0.98]">Why it matches</h3>
        <p className="text-[rgba(23,29,26,0.66)] leading-[1.7]">
          Fits your artsy, after-work, under-$40 pattern. Pair it with a quiet dinner nearby and save the later jazz set
          as backup.
        </p>
        <div className="flex flex-wrap gap-[10px] mt-[26px]">
          {['AI match', 'Insider tip', 'Complete the night'].map((tag) => (
            <span key={tag} className="min-h-[38px] border border-[rgba(23,29,26,0.12)] rounded-lg px-[10px] py-2 inline-flex items-center gap-2 bg-[rgba(255,255,255,0.58)] text-[#195339] text-[0.78rem] font-extrabold uppercase">
              {tag}
            </span>
          ))}
        </div>
      </aside>
    </section>
  );
}

function MarketingBeyondSection() {
  return (
    <section className="grid grid-cols-[minmax(320px,0.9fr)_minmax(360px,1.1fr)] gap-[clamp(28px,5vw,72px)] items-center px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-[#171d1a] text-[#f1f1f1]">
      <div>
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">Beyond discovery</p>
        <h2 className="max-w-[760px] mt-[10px] mb-[18px] text-[clamp(2.5rem,7vw,6.3rem)] leading-[0.96]">From what is happening? to we are going.</h2>
        <p className="text-[rgba(241,241,241,0.58)] leading-[1.75]">
          Aventi is built around the moment after discovery too: saved events, smarter calendars, friend-ready sharing,
          travel mode, and complete-the-night ideas that turn one good event into a real plan.
        </p>
        <a className="mt-4 inline-flex border border-[rgba(241,241,241,0.17)] rounded-lg items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[rgba(241,241,241,0.08)] text-[#f1f1f1]" href="/feed">
          <Compass size={18} />
          Try The Feed
        </a>
      </div>
      <div className="border border-[rgba(241,241,241,0.17)] rounded-lg p-[clamp(14px,2vw,22px)] bg-[linear-gradient(135deg,rgba(58,144,106,0.18),transparent),rgba(241,241,241,0.06)] shadow-[0_34px_90px_rgba(0,0,0,0.26)]" aria-label="Aventi planning features">
        {[
          { icon: <CalendarDays size={22} />, label: 'Saved calendar', value: 'Keep the shortlist close' },
          { icon: <Share2 size={22} />, label: 'Social planning', value: 'Share the exact event, not a search result' },
          { icon: <MapPin size={22} />, label: 'Travel mode', value: 'Preview a city before you land' },
          { icon: <Sparkles size={22} />, label: 'AI night builder', value: 'Dinner, show, after-hours, all in one flow' },
        ].map((row, i) => (
          <div key={row.label} className={`grid grid-cols-[auto_1fr] gap-4 items-start py-[22px] ${i > 0 ? 'border-t border-[rgba(241,241,241,0.12)]' : ''}`}>
            <div className="text-[#f9d846]">{row.icon}</div>
            <div>
              <span className="block mb-[6px] text-[rgba(241,241,241,0.58)] text-[0.72rem] font-extrabold tracking-[0.12em] uppercase">{row.label}</span>
              <strong className="block text-[clamp(1.1rem,2.4vw,1.8rem)] leading-[1.12]">{row.value}</strong>
            </div>
          </div>
        ))}
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
  const chipBase = `${motion.base} inline-flex items-center gap-2 h-9 px-3 rounded-full text-[0.8125rem] font-medium border`;
  const chipIdle = 'border-[var(--color-app-border)] bg-[var(--color-app-surface)] text-[var(--color-app-text-muted)] hover:text-[var(--color-app-text)] hover:bg-[var(--color-app-surface-2)]';
  const chipDate = 'border-[var(--color-violet-bright)]/40 bg-[rgba(107,75,255,0.14)] text-[var(--color-violet-bright)]';
  const chipCategory = 'border-[rgba(77,255,168,0.4)] bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)]';
  const chipVibe = 'border-white/30 bg-white/[0.10] text-white';
  const labelDate = (d: FeedFilters['date']) =>
    d === 'week' ? 'This week' : d === 'today' ? 'Today' : d === 'tomorrow' ? 'Tomorrow' : 'Weekend';

  return (
    <div className="flex flex-wrap gap-2" aria-label="Feed filters">
      {(['today', 'tomorrow', 'weekend', 'week'] as const).map((date) => (
        <button
          key={date}
          className={`${chipBase} ${filters.date === date ? chipDate : chipIdle}`}
          type="button"
          onClick={() => onSetDate(date)}
        >
          {labelDate(date)}
        </button>
      ))}
      {categoryOptions.map((category) => (
        <button
          key={category}
          className={`${chipBase} ${(filters.categories ?? []).includes(category) ? chipCategory : chipIdle}`}
          type="button"
          onClick={() => onToggleCategory(category)}
        >
          {categoryLabels[category]}
        </button>
      ))}
      {vibeOptions.map((vibe) => (
        <button
          key={vibe}
          className={`${chipBase} ${(filters.vibes ?? []).includes(vibe) ? chipVibe : chipIdle}`}
          type="button"
          onClick={() => onToggleVibe(vibe)}
        >
          {vibeLabels[vibe]}
        </button>
      ))}
    </div>
  );
}

function PosterIconButton({
  label,
  children,
  onClick,
  tone = 'glass',
  active = false,
}: {
  label: string;
  children: React.ReactNode;
  onClick?: () => void;
  tone?: 'glass' | 'violet';
  active?: boolean;
}) {
  const base = `${motion.base} w-11 h-11 inline-grid place-items-center rounded-full backdrop-blur-[14px] active:scale-95`;
  const glassTone =
    'bg-[rgba(7,7,13,0.55)] border border-white/15 text-white hover:bg-[rgba(7,7,13,0.75)]';
  const violetTone = active
    ? 'bg-[var(--color-violet)] border border-[var(--color-violet-bright)] text-white shadow-[var(--glow-violet)]'
    : 'bg-[rgba(107,75,255,0.18)] border border-[var(--color-violet)]/50 text-white hover:bg-[rgba(107,75,255,0.32)]';
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`${base} ${tone === 'violet' ? violetTone : glassTone}`}
    >
      {children}
    </button>
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
      className={`relative h-[calc(100dvh-176px)] [scroll-snap-align:start] overflow-hidden rounded-none md:rounded-[var(--radius-card)] md:h-auto md:min-h-[min(720px,calc(100dvh-160px))] md:mb-4 bg-[var(--color-app-bg-elev)] text-white ${motion.base} ${
        action === 'like'
          ? 'outline outline-[3px] outline-[var(--color-violet)] shadow-[var(--glow-violet)]'
          : ''
      }`}
    >
      <img src={event.imageUrl ?? heroImages[0]} alt="" className="object-cover absolute inset-0 w-full h-full" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(7,7,13,0.20),rgba(7,7,13,0.92)),linear-gradient(90deg,rgba(7,7,13,0.65),transparent_62%)]" />
      <div className="relative z-[1] flex justify-between gap-3 p-4 sm:p-5">
        <span className={`${glass.bar} rounded-full px-3 py-1.5 text-[0.75rem] font-semibold`}>
          {categoryLabels[event.category]}
        </span>
        <span className={`${glass.bar} rounded-full px-3 py-1.5 text-[0.75rem] font-semibold`}>
          {formatPrice(event)}
        </span>
      </div>
      <div className="absolute left-4 sm:left-6 right-[72px] sm:right-[108px] bottom-4 sm:bottom-6 z-[1]">
        <div className={`${glass.bar} inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[0.8125rem] font-semibold`}>
          <CalendarDays size={14} strokeWidth={1.6} />
          {formatEventTime(event.startsAt)}
        </div>
        <h2 className="max-w-[760px] mt-[14px] mb-3 text-[clamp(1.75rem,5.5vw,4.5rem)] font-extrabold leading-[1.02] tracking-[-0.01em]">
          {event.title}
        </h2>
        <p className="max-w-[580px] mb-4 text-white/78 leading-[1.55] text-[0.9375rem] sm:text-base">
          {event.description}
        </p>
        <div className="flex flex-wrap items-center gap-3 text-white/78 text-[0.875rem] font-medium">
          <span className="inline-flex gap-2 items-center"><MapPin size={14} strokeWidth={1.6} />{event.venueName}</span>
          <span className="inline-flex gap-2 items-center"><Compass size={14} strokeWidth={1.6} />{event.radiusMiles?.toFixed(1)} mi</span>
        </div>
        <div className="flex flex-wrap gap-2 mt-4">
          {event.vibes.slice(0, 4).map((vibe) => (
            <span
              key={vibe}
              className={`${glass.bar} rounded-full px-3 py-1.5 text-[0.75rem] font-medium text-white/85`}
            >
              {vibeLabels[vibe]}
            </span>
          ))}
        </div>
      </div>
      <div className="absolute right-3 sm:right-[18px] bottom-4 sm:bottom-6 z-[1] grid gap-2.5">
        <PosterIconButton label="Pass event" onClick={() => onAction('pass')}>
          <X size={20} strokeWidth={1.6} />
        </PosterIconButton>
        <PosterIconButton label="Event details" onClick={onOpen}>
          <Info size={20} strokeWidth={1.6} />
        </PosterIconButton>
        <PosterIconButton label="Share event">
          <Share2 size={19} strokeWidth={1.6} />
        </PosterIconButton>
        <PosterIconButton
          label="Save event"
          tone="violet"
          onClick={() => onAction('like')}
          active={action === 'like'}
        >
          <Heart size={20} strokeWidth={1.6} fill={action === 'like' ? 'currentColor' : 'none'} />
        </PosterIconButton>
      </div>
    </article>
  );
}

function MobileFilterSheet({
  open,
  onClose,
  filters,
  isMining,
  onToggleCategory,
  onToggleVibe,
  onSetDate,
  onRefresh,
}: {
  open: boolean;
  onClose: () => void;
  filters: FeedFilters;
  isMining: boolean;
  onToggleCategory: (c: EventCategory) => void;
  onToggleVibe: (v: EventVibeTag) => void;
  onSetDate: (d: FeedFilters['date']) => void;
  onRefresh: () => void;
}) {
  const activeCount =
    (filters.categories?.length ?? 0) +
    (filters.vibes?.length ?? 0) +
    (filters.date !== 'week' ? 1 : 0);

  // Escape closes the sheet — standard modal-dialog interaction.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const chipBase = `${motion.base} inline-flex items-center gap-2 h-9 px-3 rounded-full text-[0.8125rem] font-medium border`;
  const chipIdle =
    'border-[var(--color-app-border)] bg-[var(--color-app-surface)] text-[var(--color-app-text-muted)] hover:text-[var(--color-app-text)]';
  const chipDate =
    'border-[var(--color-violet-bright)]/40 bg-[rgba(107,75,255,0.14)] text-[var(--color-violet-bright)]';
  const chipVibe = 'border-white/30 bg-white/[0.10] text-white';

  return (
    <>
      {/* backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-[rgba(0,0,0,0.65)] backdrop-blur-[3px] transition-opacity duration-[var(--dur-base)] ease-[var(--ease-out)] ${
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      {/* sheet — bottom on mobile, centered & narrower on desktop */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="aventi-filters-title"
        // `inert` prevents focus + screen-reader access when the sheet is
        // animated off-screen, since we keep it mounted for the transition.
        // React 19+ accepts the boolean directly.
        inert={!open}
        className={`fixed bottom-0 left-0 right-0 mx-auto md:max-w-[560px] md:bottom-6 z-50 max-h-[88dvh] md:max-h-[min(720px,calc(100dvh-64px))] overflow-y-auto rounded-t-[24px] md:rounded-[var(--radius-card)] border border-[var(--color-app-border)] md:border-t md:border bg-[rgba(7,7,13,0.96)] backdrop-blur-[18px] text-white shadow-[0_-30px_80px_rgba(0,0,0,0.5)] transition-transform duration-[var(--dur-base)] ease-[var(--ease-out)] ${
          open ? 'translate-y-0' : 'translate-y-full'
        }`}
      >
        {/* drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-white/20" />
        </div>
        {/* header */}
        <div className="flex items-center justify-between px-5 pb-3 pt-1 border-b border-[var(--color-app-border)]">
          <div className="flex items-center gap-2">
            <span id="aventi-filters-title" className={type.h2}>Filters</span>
            {activeCount > 0 && (
              <span className="inline-grid place-items-center min-w-5 h-5 px-1.5 rounded-full bg-[var(--color-violet)] text-white text-[0.7rem] font-bold">
                {activeCount}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className={`${motion.fast} w-9 h-9 inline-grid place-items-center rounded-full bg-[var(--color-app-surface)] border border-[var(--color-app-border)] text-white hover:bg-[var(--color-app-surface-2)]`}
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-6">
          {/* location */}
          <div className={`flex items-center gap-3 h-11 px-3 rounded-[var(--radius-card)] ${glass.card}`}>
            <Search size={16} strokeWidth={1.6} className="text-[var(--color-app-text-muted)]" />
            <span className={type.body}>Denver, CO</span>
          </div>

          {/* date */}
          <div>
            <p className={`${type.label} text-[var(--color-app-text-muted)] mb-2`}>When</p>
            <div className="flex flex-wrap gap-2">
              {(['today', 'tomorrow', 'weekend', 'week'] as const).map((date) => {
                const label = date === 'week' ? 'This week' : date === 'today' ? 'Today' : date === 'tomorrow' ? 'Tomorrow' : 'Weekend';
                const isActive = filters.date === date;
                return (
                  <button
                    key={date}
                    className={`${chipBase} ${isActive ? chipDate : chipIdle}`}
                    type="button"
                    onClick={() => onSetDate(date)}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* categories */}
          <div>
            <p className={`${type.label} text-[var(--color-app-text-muted)] mb-2`}>Category</p>
            <div className="grid grid-cols-1 gap-2">
              {categoryOptions.map((category) => {
                const isActive = (filters.categories ?? []).includes(category);
                return (
                  <button
                    key={category}
                    type="button"
                    onClick={() => onToggleCategory(category)}
                    aria-pressed={isActive}
                    className={`${motion.base} w-full text-left rounded-[var(--radius-card)] border px-3 py-3 ${
                      isActive
                        ? 'border-[var(--color-success-neon)]/40 bg-[rgba(77,255,168,0.08)] shadow-[var(--glow-success)]'
                        : 'border-[var(--color-app-border)] bg-[var(--color-app-surface)]'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`inline-grid place-items-center w-9 h-9 rounded-[var(--radius-card)] ${
                          isActive
                            ? 'bg-[rgba(77,255,168,0.14)] text-[var(--color-success-neon)]'
                            : 'bg-[var(--color-app-surface-2)] text-[var(--color-app-text-muted)]'
                        }`}
                      >
                        {categoryIcons[category]}
                      </span>
                      <span className={`${type.body} font-semibold ${isActive ? 'text-[var(--color-success-neon)]' : 'text-white'}`}>
                        {categoryLabels[category]}
                      </span>
                      <span className={`ml-auto ${type.caption}`}>
                        {categoryTopTags[category].length} types
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {categoryTopTags[category].map((tag) => (
                        <span
                          key={tag}
                          className={`inline-flex items-center px-2 h-6 rounded-full text-[0.7rem] font-medium ${
                            isActive
                              ? 'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)]'
                              : 'bg-[var(--color-app-surface-2)] text-[var(--color-app-text-muted)]'
                          }`}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* vibes */}
          <div>
            <p className={`${type.label} text-[var(--color-app-text-muted)] mb-2`}>Vibe</p>
            <div className="flex flex-wrap gap-2">
              {vibeOptions.map((vibe) => {
                const isActive = (filters.vibes ?? []).includes(vibe);
                return (
                  <button
                    key={vibe}
                    className={`${chipBase} ${isActive ? chipVibe : chipIdle}`}
                    type="button"
                    onClick={() => onToggleVibe(vibe)}
                  >
                    {vibeLabels[vibe]}
                  </button>
                );
              })}
            </div>
          </div>

          {/* feed status */}
          <Surface elev className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className={`${type.body} font-semibold`}>
                  {isMining ? 'Mining new events…' : 'Feed ready'}
                </p>
                <p className={`${type.caption} mt-0.5`}>
                  {isMining
                    ? 'Refreshing event inventory.'
                    : '184 visible events, Denver warmed 6 min ago.'}
                </p>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={() => { onRefresh(); onClose(); }}
                leadingIcon={<RefreshCcw size={14} strokeWidth={1.6} />}
              >
                Refresh
              </Button>
            </div>
          </Surface>

          <div className="h-[72px]" />
        </div>
      </div>
    </>
  );
}


export function EventFeedPage() {
  const [events, setEvents] = useState<EventCard[]>(demoEvents);
  const [actions, setActions] = useState<Record<string, SwipeAction>>({});
  const [selectedEvent, setSelectedEvent] = useState<EventCard | null>(demoEvents[0] ?? null);
  const [isMining, setIsMining] = useState(false);
  const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false);
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

  // Open filter sheet when URL has ?filters=open. Re-runs on every nav so clicking
  // the Filters tab while already on /feed reliably opens the sheet.
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  useEffect(() => {
    if (searchParams?.get('filters') === 'open') {
      setIsFilterSheetOpen(true);
    }
  }, [searchParams]);

  const closeFilters = () => {
    setIsFilterSheetOpen(false);
    if (searchParams?.get('filters') === 'open') {
      router.replace(pathname);
    }
  };

  return (
    <AppShell active="discovery">
      <section className="px-3 sm:px-5 md:px-8 pt-4 md:pt-8 pb-6" id="feed">
        {/* Top filter chip toolbar — desktop only, mobile uses the sheet */}
        <div className="hidden md:block mb-5">
          <FilterRail
            filters={filters}
            onToggleCategory={toggleCategory}
            onToggleVibe={toggleVibe}
            onSetDate={(date) => setFilters((current) => ({ ...current, date }))}
          />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-5 items-start">
          <main
            className="h-[calc(100dvh-176px)] overflow-y-scroll [scroll-snap-type:y_mandatory] [overscroll-behavior-y:contain] md:h-[min(820px,calc(100dvh-160px))] md:overflow-y-auto pr-1"
            aria-label="Aventi event feed"
          >
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
              <Surface elev className="grid place-items-center min-h-[320px] p-7 text-center gap-3">
                <Sparkles size={28} className="text-[var(--color-violet-bright)]" />
                <h3 className={type.h1}>No matches</h3>
                <p className={type.caption}>
                  Aventi would trigger a targeted warming scan for this filter signature.
                </p>
                <Button variant="premium" size="md" onClick={refreshFeed}>
                  Mine more events
                </Button>
              </Surface>
            )}
            <div className={`hidden md:flex items-center justify-center gap-2 min-h-[72px] mb-4 ${type.caption}`}>
              <ChevronDown size={18} />
              <span>Pull past the end to mine more events</span>
            </div>
          </main>

          <aside className={`hidden xl:block xl:sticky xl:top-[24px] ${glass.cardElev} p-5`}>
            {selectedEvent ? (
              <>
                <Pill tone="violet">Selected event</Pill>
                <h3 className={`${type.h1} mt-3 mb-3`}>{selectedEvent.title}</h3>
                <p className={`${type.body} text-[var(--color-app-text-muted)]`}>
                  {selectedEvent.description}
                </p>
                <dl className="grid gap-3 mt-5">
                  {[
                    { label: 'Venue', value: selectedEvent.venueName },
                    { label: 'When', value: formatEventTime(selectedEvent.startsAt) },
                    {
                      label: 'Signal',
                      value: selectedEvent.vibes.map((vibe) => vibeLabels[vibe]).join(', '),
                    },
                  ].map((item) => (
                    <div key={item.label}>
                      <dt className={`${type.caption} !text-[var(--color-app-text-faint)]`}>
                        {item.label}
                      </dt>
                      <dd className={`${type.body} mt-1 text-[var(--color-app-text)]`}>
                        {item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
                <Button
                  variant="primary"
                  size="md"
                  fullWidth
                  className="mt-5"
                  leadingIcon={<CalendarDays size={16} strokeWidth={1.6} />}
                >
                  Get tickets
                </Button>
              </>
            ) : (
              <div className="grid place-items-center min-h-[300px] p-7 text-center gap-3">
                <Eye size={26} className="text-[var(--color-app-text-faint)]" />
                <p className={type.caption}>Select an event to inspect details.</p>
              </div>
            )}
          </aside>
        </div>
      </section>

      <MobileFilterSheet
        open={isFilterSheetOpen}
        onClose={closeFilters}
        filters={filters}
        isMining={isMining}
        onToggleCategory={toggleCategory}
        onToggleVibe={toggleVibe}
        onSetDate={(date) => setFilters((current) => ({ ...current, date }))}
        onRefresh={refreshFeed}
      />
      <AuthModal />
    </AppShell>
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
    `${motion.base} inline-flex items-center gap-2 h-9 px-3.5 rounded-full text-[0.8125rem] font-semibold ${
      activeTab === tab
        ? 'bg-[var(--color-violet)] text-white shadow-[var(--glow-violet)]'
        : 'bg-transparent text-[var(--color-app-text-muted)] hover:text-[var(--color-app-text)]'
    }`;

  const statusPill = (status: string) => {
    const tone =
      status === 'ready'
        ? 'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)] border-[var(--color-success-neon)]/40'
        : status === 'warming' || status === 'targeted_warming' || status === 'running' || status === 'queued' || status === 'completed'
        ? 'bg-[rgba(107,75,255,0.14)] text-[var(--color-violet-bright)] border-[var(--color-violet)]/40'
        : status === 'succeeded'
        ? 'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)] border-[var(--color-success-neon)]/40'
        : 'bg-[var(--color-app-surface)] text-[var(--color-app-text-muted)] border-[var(--color-app-border)]';
    return `inline-flex items-center px-2.5 h-6 rounded-full text-[0.7rem] font-semibold border ${tone}`;
  };

  return (
    <AppShell active="admin">
      <section className="px-4 sm:px-6 md:px-8 pt-6 md:pt-8 pb-12" id="admin">
        <div className="max-w-[760px] mb-8">
          <Pill tone="violet">Admin portal</Pill>
          <h1 className={`${type.display} mt-3 mb-3`}>
            Backend market scans, visible at a glance.
          </h1>
          <p className={`${type.body} text-[var(--color-app-text-muted)] max-w-[560px]`}>
            Operational views for heat tiers, inventory status, worker activity, ingest performance,
            and verification queues — kept calm, not noisy.
          </p>
        </div>

        <Surface elev className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div>
              <span className={`${type.label} text-[var(--color-app-text-muted)]`}>Operations</span>
              <h2 className={`${type.h1} mt-1`}>Chron market scan console</h2>
            </div>
            <div
              className="flex items-center gap-1 p-1 rounded-full border border-[var(--color-app-border)] bg-[var(--color-app-surface)]"
              role="tablist"
              aria-label="Admin views"
            >
              <button className={tabBtn('markets')} type="button" onClick={() => setActiveTab('markets')}>
                <Gauge size={14} strokeWidth={1.6} />
                Markets
              </button>
              <button className={tabBtn('scans')} type="button" onClick={() => setActiveTab('scans')}>
                <Activity size={14} strokeWidth={1.6} />
                Scans
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 mb-5 p-3 rounded-[var(--radius-card)] border border-[var(--color-app-border)] bg-[var(--color-app-surface)]">
            <span className={`${type.body} text-[var(--color-app-text-muted)] mr-auto`}>
              {auth.email ?? 'Admin session active'}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => loadDashboard()}
              disabled={isLoading}
              leadingIcon={<RefreshCcw size={14} strokeWidth={1.6} />}
            >
              Refresh
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => auth.signOut()}
              leadingIcon={<LogOut size={14} strokeWidth={1.6} />}
            >
              Sign out
            </Button>
          </div>

          {error ? (
            <Surface className="grid gap-3 place-items-center p-8 text-center mb-5">
              <Lock size={24} className="text-[var(--color-danger-glow)]" />
              <h3 className={type.h1}>Admin access blocked</h3>
              <p className={`${type.body} text-[var(--color-app-text-muted)] max-w-[560px]`}>
                {error.includes('403')
                  ? 'This Supabase user is signed in, but the backend rejected the admin role claim.'
                  : error}
              </p>
            </Surface>
          ) : null}

          {isLoading && !dashboard ? (
            <Surface className="grid gap-3 place-items-center p-8 text-center mb-5">
              <Loader2 size={24} className="animate-spin text-[var(--color-violet-bright)]" />
              <h3 className={type.h1}>Loading scan telemetry</h3>
              <p className={`${type.body} text-[var(--color-app-text-muted)] max-w-[560px]`}>
                Reading market inventory state, ingest runs, and verification health from the backend.
              </p>
            </Surface>
          ) : dashboard ? (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
                {[
                  { label: 'Markets', value: dashboard.rollup.marketsTotal },
                  { label: 'Hot markets', value: dashboard.rollup.hotMarkets },
                  { label: 'Active scans', value: dashboard.rollup.activeScans },
                  { label: 'Verification backlog', value: dashboard.rollup.verificationBacklog },
                ].map((metric) => (
                  <div
                    key={metric.label}
                    className={`${glass.card} p-4`}
                  >
                    <span className={`${type.label} text-[var(--color-app-text-muted)]`}>
                      {metric.label}
                    </span>
                    <strong className="block mt-2 text-[2rem] leading-none font-extrabold tracking-[-0.01em]">
                      {metric.value}
                    </strong>
                  </div>
                ))}
              </div>

              {activeTab === 'markets' ? (
                <div className={`${glass.card} overflow-x-auto`} role="table" aria-label="Market inventory state">
                  <div
                    className={`grid grid-cols-[1.3fr_1fr_0.7fr_1fr_1.1fr_0.7fr] gap-4 min-w-[860px] px-4 py-3 items-center ${type.label} text-[var(--color-app-text-muted)]`}
                    role="row"
                  >
                    <span>Market</span>
                    <span>Status</span>
                    <span>Visible</span>
                    <span>Last scan</span>
                    <span>Targeted</span>
                    <span>Active users</span>
                  </div>
                  {dashboard.markets.map((market) => {
                    const status = marketStatus(market);
                    return (
                      <div
                        className={`grid grid-cols-[1.3fr_1fr_0.7fr_1fr_1.1fr_0.7fr] gap-4 min-w-[860px] px-4 py-3 items-center border-t border-[var(--color-app-border)] ${type.body}`}
                        role="row"
                        key={market.marketKey}
                      >
                        <span>
                          <strong className="block text-[var(--color-app-text)]">{market.city}</strong>
                          <small className={`block mt-1 ${type.caption}`}>
                            {market.heatTier} · {market.state ?? market.country}
                          </small>
                        </span>
                        <span className={statusPill(status)}>{status.replace('_', ' ')}</span>
                        <span>{market.visibleEventCount7d}</span>
                        <span>{formatDateTime(market.lastScanCompletedAt ?? market.lastScanStartedAt)}</span>
                        <span>{formatDateTime(market.lastTargetedRequestedAt)}</span>
                        <span>{market.activeUserCount7d}</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="grid gap-3">
                  {dashboard.ingestRuns.map((run) => (
                    <article
                      className={`${glass.card} grid grid-cols-1 sm:grid-cols-[minmax(220px,1fr)_minmax(280px,1.3fr)_auto] gap-4 items-center p-4`}
                      key={run.id}
                    >
                      <div>
                        <span className={`${type.label} text-[var(--color-violet-bright)]`}>
                          {run.id.slice(0, 12)}
                        </span>
                        <h4 className={`${type.h2} my-1`}>
                          {run.city ?? 'Unknown market'} · {run.sourceType ?? 'source'}
                        </h4>
                        <p className={type.caption}>
                          {run.sourceName ?? 'ingest'} started {formatDateTime(run.startedAt)}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {[
                          `${run.discoveredCount} found`,
                          `${run.insertedCount} inserted`,
                          formatDateTime(run.finishedAt),
                          run.errorMessage ? 'error' : 'clean',
                        ].map((s) => (
                          <span
                            key={s}
                            className="rounded-full px-2.5 h-6 inline-flex items-center bg-[var(--color-app-surface)] border border-[var(--color-app-border)] text-[0.7rem] font-medium text-[var(--color-app-text-muted)]"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                      <strong className={statusPill(run.status)}>{run.status}</strong>
                    </article>
                  ))}
                  <article
                    className={`${glass.card} grid grid-cols-1 sm:grid-cols-[minmax(220px,1fr)_minmax(280px,1.3fr)_auto] gap-4 items-center p-4`}
                  >
                    <div>
                      <span className={`${type.label} text-[var(--color-violet-bright)]`}>
                        verification
                      </span>
                      <h4 className={`${type.h2} my-1`}>Verification health</h4>
                      <p className={type.caption}>
                        {dashboard.workerQueue.configured
                          ? 'Worker queue configured'
                          : 'Worker queue not configured'}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {dashboard.verification.slice(0, 4).map((item) => (
                        <span
                          key={`${item.status}-${String(item.active)}`}
                          className="rounded-full px-2.5 h-6 inline-flex items-center bg-[var(--color-app-surface)] border border-[var(--color-app-border)] text-[0.7rem] font-medium text-[var(--color-app-text-muted)]"
                        >
                          {item.status}: {item.count}
                        </span>
                      ))}
                    </div>
                    <strong className={statusPill('ready')}>
                      {dashboard.workerQueue.pollSeconds}s poll
                    </strong>
                  </article>
                </div>
              )}
            </>
          ) : null}
        </Surface>
      </section>
      <AuthModal />
    </AppShell>
  );
}

function PricingSection() {
  return (
    <section className="px-[clamp(16px,4vw,64px)] py-[clamp(62px,8vw,110px)]" id="premium">
      <div className="w-[min(800px,100%)] mb-[34px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-[#f9d846]">Aventi Premium</p>
        <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">Start free. Upgrade when you want the whole city.</h2>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {[
          {
            icon: <User size={22} />,
            title: 'Free Discovery',
            desc: 'Browse local events, save favorites, share plans, and teach the feed what kind of nights you want more of.',
            features: ['Daily discovery feed', 'Saved events and favorites', 'Basic vibe and distance filters'],
            cta: 'Launch Aventi',
          },
          {
            icon: <ShieldCheck size={22} />,
            title: 'Premium',
            desc: 'Unlock deeper search, trip planning, and AI context for people who want Aventi to become their city guide.',
            features: ['Unlimited swipes', 'Travel mode and advanced filters', 'Insider tips and complete-the-night ideas'],
            cta: 'Explore Premium',
          },
        ].map((plan) => (
          <article key={plan.title} className="border border-[rgba(23,29,26,0.14)] rounded-lg bg-[rgba(255,255,255,0.48)] shadow-[0_24px_70px_rgba(23,29,26,0.2)] p-[clamp(22px,3vw,34px)]">
            {plan.icon}
            <h3 className="mt-[18px] mb-2 text-[clamp(1.4rem,3vw,2.6rem)]">{plan.title}</h3>
            <p className="text-[rgba(23,29,26,0.62)] leading-[1.7]">{plan.desc}</p>
            <ul className="grid gap-[10px] mt-[18px] p-0 list-none">
              {plan.features.map((f) => (
                <li key={f} className="relative pl-6 text-[rgba(23,29,26,0.66)] leading-[1.55] before:absolute before:left-0 before:top-[0.45em] before:w-2 before:h-2 before:rounded-full before:bg-[#3a906a] before:content-['']">{f}</li>
              ))}
            </ul>
            <a href="/feed" className="mt-[14px] border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[#f9d846] text-[#171d1a]">{plan.cta}</a>
          </article>
        ))}
      </div>
    </section>
  );
}


export function SavedPage() {
  // No save persistence yet — placeholder empty state.
  const savedEvents: EventCard[] = [];

  return (
    <AppShell active="saved">
      <div className="mx-auto w-full max-w-[760px] px-4 sm:px-6 pt-6 pb-12">
        <div className="flex items-center gap-3 mb-6">
          <h1 className={type.h1}>Saved events</h1>
          <Pill tone="violet">{savedEvents.length}</Pill>
        </div>

        {savedEvents.length === 0 ? (
          <Surface elev className="px-6 py-10 text-center grid place-items-center gap-4">
            <span className="w-14 h-14 rounded-full bg-[rgba(107,75,255,0.14)] text-[var(--color-violet-bright)] inline-grid place-items-center">
              <Heart size={24} strokeWidth={1.6} />
            </span>
            <div>
              <h2 className={type.h2}>Nothing saved yet</h2>
              <p className={`${type.body} text-[var(--color-app-text-muted)] mt-1 max-w-[36ch] mx-auto`}>
                Tap the heart on any event in Discovery to save it for later.
              </p>
            </div>
            <ButtonLink
              href="/feed"
              variant="premium"
              size="md"
              leadingIcon={<Compass size={16} strokeWidth={1.6} />}
            >
              Browse discovery
            </ButtonLink>
          </Surface>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {savedEvents.map((event) => (
              <a
                key={event.id}
                href={event.bookingUrl ?? '/feed'}
                className={`${motion.base} ${glass.card} overflow-hidden hover:bg-[var(--color-app-surface-2)]`}
              >
                <div
                  className="aspect-[16/10] bg-cover bg-center"
                  style={{ backgroundImage: event.imageUrl ? `url(${event.imageUrl})` : undefined }}
                  aria-hidden
                />
                <div className="p-4">
                  <p className={`${type.label} text-[var(--color-violet-bright)]`}>
                    {formatEventTime(event.startsAt)}
                  </p>
                  <h3 className={`${type.h2} mt-1`}>{event.title}</h3>
                  <p className={`${type.caption} mt-1`}>
                    {event.venueName} · {formatPrice(event)}
                  </p>
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
      <AuthModal />
    </AppShell>
  );
}

export function ProfilePage() {
  const auth = useAuthSession();
  // No premium signal in useAuthSession yet — placeholder until entitlements wire-up.
  const isPremium = false;

  const displayName = useMemo(() => {
    if (!auth.email) return 'Guest Explorer';
    const local = auth.email.split('@')[0]?.replace(/[._-]+/g, ' ') ?? '';
    const titled = local.replace(/\b\w/g, (c) => c.toUpperCase());
    return titled || 'Aventi Explorer';
  }, [auth.email]);

  return (
    <AppShell active="profile">
      <div className="mx-auto w-full max-w-[640px] px-5 pt-10 pb-12">
        {/* Identity card */}
        <Surface elev className="px-6 py-7 flex flex-col items-center text-center">
          <div
            className="w-28 h-28 rounded-full p-[3px] inline-grid place-items-center"
            style={
              isPremium
                ? {
                    background:
                      'conic-gradient(from 200deg, #A67CFF 0deg, #6B4BFF 140deg, #A67CFF 360deg)',
                  }
                : { background: 'rgba(255,255,255,0.08)' }
            }
          >
            <div className="w-full h-full rounded-full bg-[var(--color-app-bg)] inline-grid place-items-center">
              <img src="/brand/icon.png" alt="" className="w-12 h-12 opacity-90" />
            </div>
          </div>
          <h1 className={`${type.display} mt-5`}>{displayName}</h1>
          <Pill tone={isPremium ? 'premium' : 'neutral'} className="mt-3">
            {isPremium ? 'Premium' : 'Freemium access'}
          </Pill>
        </Surface>

        {/* Premium CTA */}
        {!isPremium && (
          <button
            type="button"
            onClick={() => auth.openAuthPrompt('premium')}
            className={`${motion.base} mt-5 w-full rounded-[var(--radius-card)] px-5 py-4 flex items-center gap-4 text-left text-white shadow-[var(--glow-violet)] hover:brightness-110 active:scale-[0.99] [background:var(--gradient-premium)]`}
          >
            <div className="flex-1 min-w-0">
              <p className={type.h2}>Unlock everything</p>
              <p className="mt-0.5 text-[0.8125rem] font-medium text-white/80">
                Get unlimited swipes
              </p>
            </div>
            <span className="shrink-0 w-10 h-10 rounded-full bg-white inline-grid place-items-center text-[var(--color-violet)]">
              <Sparkles size={18} strokeWidth={1.6} />
            </span>
          </button>
        )}

        {/* Links */}
        <ul className="mt-6 flex flex-col gap-3">
          <li>
            <a
              href="/terms"
              className={`${motion.base} ${glass.card} flex items-center gap-3 px-4 py-4 hover:bg-[var(--color-app-surface-2)]`}
            >
              <span className="w-9 h-9 rounded-[var(--radius-card)] bg-[rgba(166,124,255,0.14)] text-[var(--color-violet-bright)] inline-grid place-items-center">
                <Info size={16} strokeWidth={1.6} />
              </span>
              <span className={`${type.body} flex-1 text-[var(--color-app-text)]`}>Terms</span>
              <ChevronRight size={16} className="text-[var(--color-app-text-faint)]" />
            </a>
          </li>
          <li>
            <a
              href="/privacy"
              className={`${motion.base} ${glass.card} flex items-center gap-3 px-4 py-4 hover:bg-[var(--color-app-surface-2)]`}
            >
              <span className="w-9 h-9 rounded-[var(--radius-card)] bg-[rgba(77,255,168,0.12)] text-[var(--color-success-neon)] inline-grid place-items-center">
                <ShieldCheck size={16} strokeWidth={1.6} />
              </span>
              <span className={`${type.body} flex-1 text-[var(--color-app-text)]`}>Privacy</span>
              <ChevronRight size={16} className="text-[var(--color-app-text-faint)]" />
            </a>
          </li>
        </ul>

        {/* Permanent download CTA */}
        <ButtonLink
          href="#get-app"
          variant="secondary"
          size="lg"
          fullWidth
          className="mt-6"
          leadingIcon={<Smartphone size={18} strokeWidth={1.6} />}
        >
          Download the app
        </ButtonLink>

        {/* Sign out / sign in */}
        {auth.isAuthenticated ? (
          <Button
            variant="ghost"
            size="lg"
            fullWidth
            className="mt-3"
            onClick={() => auth.signOut()}
          >
            Sign out
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="lg"
            fullWidth
            className="mt-3"
            onClick={() => auth.openAuthPrompt('welcome')}
          >
            Sign in
          </Button>
        )}

        {/* Destructive */}
        <Button variant="destructive" size="md" fullWidth className="mt-5 !border-transparent">
          Delete account
        </Button>
      </div>
      <AuthModal />
    </AppShell>
  );
}

export function MarketingHome() {
  return (
    <>
      <MarketingHero />
      <MarketingProductSection />
      <MarketingFlowSection />
      <MarketingVibeSection />
      <MarketingDetailsSection />
      <MarketingBeyondSection />
      <PricingSection />
      <footer className="flex items-center justify-between gap-[18px] px-[clamp(16px,4vw,64px)] py-6 border-t border-[rgba(23,29,26,0.14)]">
        <LogoMark />
        <span className="text-[rgba(23,29,26,0.55)] text-[0.72rem] font-bold tracking-[0.16em] uppercase text-center">Built from the Aventi brand system: Poppins, matte tones, generous space, and calm confidence.</span>
        <Check size={18} />
      </footer>
      <button
        className="fixed right-[18px] bottom-[18px] z-30 w-11 h-11 border border-[rgba(23,29,26,0.14)] rounded-lg inline-grid place-items-center bg-[rgba(241,241,241,0.88)] shadow-[0_24px_70px_rgba(23,29,26,0.2)] backdrop-blur-[18px]"
        type="button"
        aria-label="Scroll down"
        onClick={() => window.scrollBy({ top: window.innerHeight, behavior: 'smooth' })}
      >
        <ArrowDown size={18} />
      </button>
      <AuthModal />
    </>
  );
}
