'use client';

import { useEffect, useState } from 'react';
import {
  ArrowDown,
  Bell,
  CalendarDays,
  Check,
  Compass,
  Filter,
  Heart,
  LogOut,
  MapPin,
  Menu,
  Music2,
  Palette,
  Play,
  Share2,
  ShieldCheck,
  Sparkles,
  User,
  X,
} from 'lucide-react';
import type { EventCard } from '@aventi/contracts';
import { categoryLabels, demoEvents, heroImages, vibeLabels } from '@/lib/demo-data';
import { formatEventTime, formatPrice } from '@/lib/format';
import { useAuthSession } from '@/lib/auth-session';
import { AuthModal } from '../AuthModal';
import { motion } from '../ui/app-ui';

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
    ? 'bg-forest text-cream border-[rgba(241,241,241,0.12)]'
    : 'bg-cream text-charcoal border-[rgba(23,29,26,0.12)]';
  const divider = isDark ? 'border-[rgba(241,241,241,0.1)]' : 'border-[rgba(23,29,26,0.1)]';
  const linkBase = 'flex items-center gap-3 rounded-lg px-4 py-3 text-[1rem] font-bold transition-colors';
  const linkActive = isDark
    ? 'bg-[rgba(249,216,70,0.12)] text-mellow'
    : 'bg-[rgba(25,83,57,0.1)] text-forest';
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
            href="/profile"
            className="flex items-center gap-3 rounded-lg px-4 py-3 font-bold bg-mellow text-charcoal"
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
      className={`rounded-lg px-[10px] py-[9px] ${active === key ? 'bg-[rgba(25,83,57,0.12)] text-forest' : 'text-[rgba(23,29,26,0.64)]'}`}
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
        className="hidden sm:inline-flex border-0 rounded-lg items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow text-charcoal"
        href="/#pricing"
      >
        Get App
      </a>
      {/* Auth pill */}
      {mounted ? (
        auth.isAuthenticated ? (
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] px-3 h-[42px] text-[0.82rem] font-bold text-charcoal hover:bg-[rgba(23,29,26,0.1)]"
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
            className="inline-flex items-center gap-2 rounded-lg border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] px-3 h-[42px] text-[0.82rem] font-bold text-charcoal hover:bg-[rgba(23,29,26,0.1)]"
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
        className="sm:hidden w-[42px] h-[42px] rounded-lg inline-grid place-items-center border border-[rgba(23,29,26,0.14)] bg-[rgba(23,29,26,0.06)] text-charcoal"
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
      <header className="sticky top-0 z-40 flex items-center justify-between gap-[18px] min-h-[72px] px-[clamp(16px,4vw,64px)] py-[14px] border-b border-[rgba(23,29,26,0.14)] bg-[rgba(241,241,241,0.92)] text-charcoal backdrop-blur-[18px]">
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
    ghost: 'border-[rgba(241,241,241,0.17)] bg-[rgba(241,241,241,0.08)] text-cream',
    dark: 'border-[rgba(241,241,241,0.17)] bg-[rgba(23,29,26,0.72)] text-cream',
    yellow: 'border-[rgba(249,216,70,0.7)] bg-mellow text-charcoal',
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
    <section className="relative min-h-[92vh] overflow-hidden bg-forest text-cream" id="top">
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
          <a className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow text-charcoal" href="/feed">
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
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">Connected. Explorative. In flow.</p>
        <h1 className="mt-[10px] mb-[18px] text-[clamp(4.5rem,16vw,12rem)] leading-[0.86] uppercase">Aventi</h1>
        <p className="max-w-[650px] m-0 text-[rgba(241,241,241,0.78)] text-[clamp(1.02rem,1.4vw,1.3rem)] leading-[1.7]">
          A vertical event discovery app for nights out, new neighborhoods, and plans that should feel easy to say yes
          to. Tell Aventi your vibe, then scroll real events that fit your time, radius, budget, and mood.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-[30px]">
          <a href="/feed" className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow text-charcoal">
            <Play size={18} />
            Explore Events
          </a>
          <a href="#how-it-works" className="border border-[rgba(241,241,241,0.17)] rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[rgba(241,241,241,0.08)] text-cream">
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
    <section className="grid grid-cols-1 lg:grid-cols-[minmax(280px,0.82fr)_minmax(360px,1.18fr)] gap-[clamp(28px,5vw,72px)] items-center px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-cream" id="product">
      <div>
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">Member product</p>
        <h2 className="max-w-[760px] mt-[10px] mb-[18px] text-[clamp(2.5rem,7vw,6.3rem)] leading-[0.96]">Scroll until something feels worth leaving the house for.</h2>
        <p className="text-[rgba(23,29,26,0.62)] leading-[1.75]">
          Aventi brings the mobile feed to web without losing the core interaction: one event at a time, fast preference
          signals, useful details close at hand, and a saved list for plans you actually want to make.
        </p>
        <div className="flex flex-wrap items-center gap-[18px] mt-[28px]">
          <a className="border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow text-charcoal" href="/feed">
            <Compass size={18} />
            Open Event Feed
          </a>
          <a className="border-b-2 border-[rgba(25,83,57,0.28)] text-forest font-extrabold" href="#premium">
            See Premium
          </a>
        </div>
      </div>
      <div className="relative min-h-[680px] border border-[rgba(23,29,26,0.12)] rounded-lg overflow-hidden bg-[linear-gradient(135deg,rgba(25,83,57,0.92),rgba(58,144,106,0.74)),#032F25]" aria-label="Aventi feed preview">
        <div className="absolute left-[clamp(18px,5vw,70px)] top-1/2 -translate-y-1/2 w-[min(330px,calc(100%-36px))] border-[10px] border-charcoal rounded-[34px] overflow-hidden bg-forest shadow-[0_30px_80px_rgba(0,0,0,0.32)]">
          <div className="flex justify-between px-[18px] pt-[18px] pb-3 text-[rgba(241,241,241,0.68)] text-[0.72rem] font-extrabold tracking-[0.12em] uppercase">
            <span>Aventi</span>
            <span>Tonight</span>
          </div>
          <div className="relative min-h-[480px] flex items-end">
            <img src={leadEvent.imageUrl ?? heroImages[0]} alt="" className="object-cover absolute inset-0 w-full h-full" />
            <div className="absolute inset-0 bg-[linear-gradient(180deg,transparent,rgba(23,29,26,0.88))]" />
            <div className="relative z-[1] px-[18px] pb-[22px] text-cream">
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
          <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-pine">Next in queue</span>
          <h3 className="mt-[9px] mb-[10px] text-[clamp(1.35rem,3vw,2.3rem)] leading-[1.05]">{secondEvent.title}</h3>
          <p className="text-[rgba(23,29,26,0.62)] leading-[1.75]">{secondEvent.description}</p>
          <div className="flex flex-wrap gap-2 mt-[18px]">
            {secondEvent.vibes.slice(0, 3).map((vibe) => (
              <span key={vibe} className="border border-[rgba(23,29,26,0.12)] rounded-lg px-[10px] py-[7px] bg-[rgba(25,83,57,0.08)] text-forest text-[0.76rem] font-bold uppercase">{vibeLabels[vibe]}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketingFlowSection() {
  return (
    <section className="px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-sand" id="how-it-works">
      <div className="w-[min(800px,100%)] mb-[34px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">How it works</p>
        <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">A feed that learns your vibe, then opens up the city.</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 border-t border-[rgba(23,29,26,0.16)]">
        {[
          { num: '01', title: 'Set the night', body: 'Pick where you are, how far you will go, what you are into, and whether the evening is casual or big.' },
          { num: '02', title: 'Swipe with intent', body: 'Pass, save, share, or open details. Each signal teaches Aventi what should show up next.' },
          { num: '03', title: 'Build the plan', body: 'Save the standouts, get insider context, add tickets or maps, and keep a short list for the group chat.' },
        ].map((step, i) => (
          <article key={step.num} className={`min-h-[280px] p-[clamp(22px,3vw,38px)] ${i < 2 ? 'border-r border-[rgba(23,29,26,0.16)]' : ''}`}>
            <span className="text-[0.72rem] font-extrabold tracking-[0.12em] uppercase text-pine">{step.num}</span>
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
    <section className="px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-cream">
      <div className="w-[min(800px,100%)] mb-[34px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">Vibe check</p>
        <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">Not another directory. A shortcut to your kind of night.</h2>
        <p className="max-w-[660px] text-[rgba(23,29,26,0.62)] leading-[1.75]">
          Aventi starts with the signals people actually use when they make plans: location, radius, date, budget,
          energy level, and the scenes they want more of.
        </p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-[14px]" aria-label="Aventi vibe setup">
        {[
          { icon: <MapPin size={22} />, label: 'Where', value: 'Denver within 8 miles' },
          { icon: <CalendarDays size={22} />, label: 'When', value: 'Tonight after 7' },
          { icon: <Sparkles size={22} />, label: 'Vibe', value: 'Romantic, artsy, low-key' },
          { icon: <Filter size={22} />, label: 'Budget', value: 'Free to moderate' },
        ].map((item) => (
          <article key={item.label} className="min-h-[230px] border border-[rgba(23,29,26,0.12)] rounded-lg p-[clamp(20px,2.5vw,30px)] flex flex-col justify-between bg-[linear-gradient(180deg,rgba(58,144,106,0.08),transparent),rgba(255,255,255,0.72)]">
            <div className="text-pine">{item.icon}</div>
            <div>
              <span className="block text-[rgba(23,29,26,0.5)] text-[0.72rem] font-extrabold tracking-[0.12em] uppercase">{item.label}</span>
              <strong className="block mt-[10px] text-charcoal text-[clamp(1.15rem,2.5vw,2rem)] leading-[1.08]">{item.value}</strong>
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
    <section className="grid grid-cols-1 lg:grid-cols-[minmax(420px,1.35fr)_minmax(280px,0.65fr)] gap-4 items-stretch px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-moss/30">
      <div className="border border-[rgba(23,29,26,0.12)] rounded-lg bg-[rgba(255,255,255,0.52)] shadow-[0_24px_70px_rgba(23,29,26,0.2)] grid grid-cols-1 md:grid-cols-[minmax(260px,0.85fr)_minmax(320px,1.15fr)] overflow-hidden">
        <img src={event.imageUrl ?? heroImages[2]} alt="" className="w-full h-full min-h-[520px] object-cover" />
        <div className="p-[clamp(26px,5vw,58px)] flex flex-col justify-center">
          <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">Event details</p>
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
              <span key={item.label} className="min-h-[38px] border border-[rgba(23,29,26,0.12)] rounded-lg px-[10px] py-2 inline-flex items-center gap-2 bg-[rgba(255,255,255,0.58)] text-forest text-[0.78rem] font-extrabold uppercase">
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
        <span className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-pine">Premium insight</span>
        <h3 className="my-3 text-[clamp(1.8rem,4vw,3.7rem)] leading-[0.98]">Why it matches</h3>
        <p className="text-[rgba(23,29,26,0.66)] leading-[1.7]">
          Fits your artsy, after-work, under-$40 pattern. Pair it with a quiet dinner nearby and save the later jazz set
          as backup.
        </p>
        <div className="flex flex-wrap gap-[10px] mt-[26px]">
          {['AI match', 'Insider tip', 'Complete the night'].map((tag) => (
            <span key={tag} className="min-h-[38px] border border-[rgba(23,29,26,0.12)] rounded-lg px-[10px] py-2 inline-flex items-center gap-2 bg-[rgba(255,255,255,0.58)] text-forest text-[0.78rem] font-extrabold uppercase">
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
    <section className="grid grid-cols-1 lg:grid-cols-[minmax(320px,0.9fr)_minmax(360px,1.1fr)] gap-[clamp(28px,5vw,72px)] items-center px-[clamp(16px,4vw,64px)] py-[clamp(68px,9vw,124px)] bg-forest text-cream">
      <div>
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">Beyond discovery</p>
        <h2 className="max-w-[760px] mt-[10px] mb-[18px] text-[clamp(2.5rem,7vw,6.3rem)] leading-[0.96]">From what is happening? to we are going.</h2>
        <p className="text-[rgba(241,241,241,0.58)] leading-[1.75]">
          Aventi is built around the moment after discovery too: saved events, smarter calendars, friend-ready sharing,
          travel mode, and complete-the-night ideas that turn one good event into a real plan.
        </p>
        <a className="mt-4 inline-flex border border-[rgba(241,241,241,0.17)] rounded-lg items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-[rgba(241,241,241,0.08)] text-cream" href="/feed">
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
            <div className="text-mellow">{row.icon}</div>
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

function PricingSection() {
  return (
    <section className="px-[clamp(16px,4vw,64px)] py-[clamp(62px,8vw,110px)]" id="premium">
      <div className="w-[min(800px,100%)] mb-[34px]">
        <p className="text-[0.72rem] font-bold tracking-[0.16em] uppercase text-mellow">Aventi Premium</p>
        <h2 className="mt-2 mb-3 text-[clamp(2rem,5vw,4.1rem)] leading-[1.02]">Start free. Upgrade when you want the whole city.</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                <li key={f} className="relative pl-6 text-[rgba(23,29,26,0.66)] leading-[1.55] before:absolute before:left-0 before:top-[0.45em] before:w-2 before:h-2 before:rounded-full before:bg-pine before:content-['']">{f}</li>
              ))}
            </ul>
            <a href="/feed" className="mt-[14px] border-0 rounded-lg inline-flex items-center justify-center gap-[10px] min-h-[44px] px-[18px] font-bold bg-mellow text-charcoal">{plan.cta}</a>
          </article>
        ))}
      </div>
    </section>
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
