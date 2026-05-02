'use client';

import { useEffect, useState, type ReactNode } from 'react';
import {
  Compass,
  Heart,
  Home,
  SlidersHorizontal,
  User,
  X,
  Smartphone,
} from 'lucide-react';

import { glass, motion, type } from './app-ui';

export type AppRoute = 'discovery' | 'filters' | 'saved' | 'profile' | 'admin';

interface NavItem {
  key: AppRoute;
  label: string;
  href: string;
  icon: ReactNode;
}

const navItems: NavItem[] = [
  { key: 'discovery', label: 'Discovery', href: '/feed', icon: <Compass size={20} strokeWidth={1.6} /> },
  { key: 'filters', label: 'Filters', href: '/feed?filters=open', icon: <SlidersHorizontal size={20} strokeWidth={1.6} /> },
  { key: 'saved', label: 'Saved', href: '/saved', icon: <Heart size={20} strokeWidth={1.6} /> },
  { key: 'profile', label: 'Profile', href: '/profile', icon: <User size={20} strokeWidth={1.6} /> },
];

const BANNER_DISMISS_KEY = 'aventi:download-banner-dismissed';

// ── Download App Banner ───────────────────────────────────────────────────

function DownloadAppBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      className={`fixed top-0 inset-x-0 z-50 ${glass.bar} ${motion.base}`}
      role="region"
      aria-label="Download the app"
    >
      <div className="mx-auto flex items-center justify-between gap-3 px-4 py-2.5 max-w-screen-xl">
        <div className="flex items-center gap-3 min-w-0">
          <span className="hidden sm:inline-grid place-items-center w-8 h-8 rounded-full bg-[var(--color-app-surface-2)] text-[var(--color-violet-bright)]">
            <Smartphone size={16} strokeWidth={1.6} />
          </span>
          <p className={`${type.body} text-[var(--color-app-text)] truncate`}>
            <span className="font-semibold">Download the Aventi app</span>{' '}
            <span className="text-[var(--color-app-text-muted)] hidden sm:inline">
              — discover events on the go
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <a
            href="#get-app"
            className={`${motion.base} inline-flex items-center h-9 px-4 rounded-full text-[0.8125rem] font-semibold text-white [background:var(--gradient-premium)] hover:brightness-110 active:scale-[0.98]`}
          >
            Get App
          </a>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss banner"
            className={`${motion.fast} w-8 h-8 inline-grid place-items-center rounded-full text-[var(--color-app-text-muted)] hover:bg-[var(--color-app-surface)] hover:text-[var(--color-app-text)]`}
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Back-to-website floating glass house button ──────────────────────────

function BackToWebsiteButton({ topOffset }: { topOffset: number }) {
  return (
    <a
      href="/"
      aria-label="Exit to Aventi website"
      title="Back to Aventi website"
      className={`fixed left-4 z-40 inline-grid place-items-center w-11 h-11 rounded-full text-[var(--color-app-text)] ${glass.bar} ${motion.base} hover:scale-105 hover:text-[var(--color-violet-bright)] active:scale-95`}
      style={{ top: `${topOffset + 16}px` }}
    >
      <Home size={18} strokeWidth={1.6} />
    </a>
  );
}

// ── Left Nav Rail (desktop/tablet, ≥ md) ─────────────────────────────────

function LeftNavRail({ active, topOffset }: { active?: AppRoute; topOffset: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <nav
      aria-label="App navigation"
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
      onFocus={() => setExpanded(true)}
      onBlur={() => setExpanded(false)}
      className={`hidden md:flex fixed left-0 z-30 flex-col py-6 px-3 gap-2 border-r border-[var(--color-app-border)] bg-[rgba(7,7,13,0.85)] backdrop-blur-[18px] ${motion.base}`}
      style={{
        top: `${topOffset}px`,
        bottom: 0,
        width: expanded ? '240px' : '84px',
      }}
    >
      <div className="h-[60px]" /> {/* clearance for the floating exit button */}
      {navItems.map((item) => {
        const isActive = active === item.key;
        return (
          <a
            key={item.key}
            href={item.href}
            aria-current={isActive ? 'page' : undefined}
            className={`${motion.base} flex items-center gap-3 h-12 rounded-[var(--radius-card)] px-3 ${
              isActive
                ? 'bg-[rgba(107,75,255,0.16)] text-white shadow-[inset_0_0_0_1px_rgba(107,75,255,0.4)]'
                : 'text-[var(--color-app-text-muted)] hover:bg-[var(--color-app-surface)] hover:text-[var(--color-app-text)]'
            }`}
          >
            <span className="shrink-0 inline-grid place-items-center w-10 h-10 rounded-[var(--radius-card)]">
              <span className={isActive ? 'text-[var(--color-violet-bright)]' : ''}>{item.icon}</span>
            </span>
            <span
              className={`${motion.base} text-[0.9375rem] font-semibold whitespace-nowrap overflow-hidden`}
              style={{
                opacity: expanded ? 1 : 0,
                maxWidth: expanded ? '160px' : '0',
              }}
            >
              {item.label}
            </span>
          </a>
        );
      })}
    </nav>
  );
}

// ── Bottom Tab Bar (mobile only, < md) ───────────────────────────────────

function BottomTabBar({ active }: { active?: AppRoute }) {
  return (
    <nav
      aria-label="App navigation"
      className={`md:hidden fixed bottom-0 inset-x-0 z-30 flex items-stretch h-[68px] safe-area-inset-bottom border-t border-[var(--color-app-border)] bg-[rgba(7,7,13,0.92)] backdrop-blur-[18px]`}
    >
      {navItems.map((item) => {
        const isActive = active === item.key;
        return (
          <a
            key={item.key}
            href={item.href}
            aria-current={isActive ? 'page' : undefined}
            className={`${motion.base} flex flex-col items-center justify-center gap-1 flex-1 ${
              isActive ? 'text-white' : 'text-[var(--color-app-text-faint)]'
            }`}
          >
            <span className={isActive ? 'text-[var(--color-violet-bright)]' : ''}>{item.icon}</span>
            <span className={`${type.label} ${isActive ? 'opacity-100' : 'opacity-80'}`}>
              {item.label}
            </span>
          </a>
        );
      })}
    </nav>
  );
}

// ── Top-level App Shell ──────────────────────────────────────────────────

interface AppShellProps {
  active?: AppRoute;
  /** Hide the left rail + bottom bar (e.g. for full-bleed flows). */
  chromeless?: boolean;
  children: ReactNode;
}

export function AppShell({ active, chromeless = false, children }: AppShellProps) {
  // Banner visibility — initialized to false on SSR; resolved on client mount.
  const [bannerVisible, setBannerVisible] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
    try {
      const dismissed = window.localStorage.getItem(BANNER_DISMISS_KEY) === '1';
      setBannerVisible(!dismissed);
    } catch {
      setBannerVisible(true);
    }
  }, []);

  const dismissBanner = () => {
    setBannerVisible(false);
    try {
      window.localStorage.setItem(BANNER_DISMISS_KEY, '1');
    } catch {
      /* noop */
    }
  };

  const bannerHeight = hydrated && bannerVisible ? 56 : 0;

  return (
    <div className="min-h-screen text-[var(--color-app-text)] bg-[var(--color-app-bg)]"
      style={{
        backgroundImage:
          'radial-gradient(1200px 600px at 18% -10%, rgba(166,124,255,0.14), transparent 60%), radial-gradient(900px 600px at 110% 110%, rgba(58,80,180,0.12), transparent 60%)',
      }}
    >
      {bannerVisible && <DownloadAppBanner onDismiss={dismissBanner} />}
      <BackToWebsiteButton topOffset={bannerHeight} />
      {!chromeless && <LeftNavRail active={active} topOffset={bannerHeight} />}

      <main
        className={motion.base}
        style={{
          paddingTop: `${bannerHeight}px`,
          paddingLeft: chromeless ? 0 : undefined,
          paddingBottom: chromeless ? 0 : 84, // reserve for mobile tab bar (overridden md+ via class below)
          minHeight: '100vh',
        }}
      >
        <div className={chromeless ? '' : 'md:pl-[84px] md:pb-0'}>{children}</div>
      </main>

      {!chromeless && <BottomTabBar active={active} />}
    </div>
  );
}
