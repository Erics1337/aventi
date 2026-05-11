'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import type { Session } from '@supabase/supabase-js';
import {
  Activity,
  ArrowDown,
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  Clock,
  Code2,
  Compass,
  Dumbbell,
  Eye,
  Filter,
  Gauge,
  Import,
  Heart,
  Info,
  Leaf,
  Loader2,
  Lock,
  MapPin,
  Menu,
  Mountain,
  Music2,
  Palette,
  PartyPopper,
  Play,
  RefreshCcw,
  Search,
  Share2,
  ShieldCheck,
  Smartphone,
  SlidersHorizontal,
  Store,
  Theater,
  Sparkles,
  User,
  Users,
  UtensilsCrossed,
  X,
} from 'lucide-react';
import type {
  AdminDashboardResponse,
  AdminMarketSummary,
  AdminUserLocationPoint,
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

type LatLng = { lat: number; lng: number };

function geoBounds(points: LatLng[]): { minLat: number; maxLat: number; minLng: number; maxLng: number } {
  if (points.length === 0) {
    return { minLat: 30, maxLat: 31, minLng: -98, maxLng: -97 };
  }
  let minLat = points[0].lat;
  let maxLat = points[0].lat;
  let minLng = points[0].lng;
  let maxLng = points[0].lng;
  for (const p of points) {
    minLat = Math.min(minLat, p.lat);
    maxLat = Math.max(maxLat, p.lat);
    minLng = Math.min(minLng, p.lng);
    maxLng = Math.max(maxLng, p.lng);
  }
  const padLat = Math.max((maxLat - minLat) * 0.12, 0.08);
  const padLng = Math.max((maxLng - minLng) * 0.12, 0.08);
  return {
    minLat: minLat - padLat,
    maxLat: maxLat + padLat,
    minLng: minLng - padLng,
    maxLng: maxLng + padLng,
  };
}

function projectToPercent(lat: number, lng: number, b: ReturnType<typeof geoBounds>) {
  const latSpan = Math.max(b.maxLat - b.minLat, 1e-6);
  const lngSpan = Math.max(b.maxLng - b.minLng, 1e-6);
  const x = ((lng - b.minLng) / lngSpan) * 100;
  const y = (1 - (lat - b.minLat) / latSpan) * 100;
  return {
    left: `${Math.min(96, Math.max(4, x))}%`,
    top: `${Math.min(96, Math.max(4, y))}%`,
  };
}

function AdminPeopleMap({
  users,
  markets,
}: {
  users: AdminUserLocationPoint[];
  markets: AdminMarketSummary[];
}) {
  const marketCenters: LatLng[] = markets
    .filter(
      (m) =>
        typeof m.centerLatitude === 'number' &&
        typeof m.centerLongitude === 'number' &&
        !Number.isNaN(m.centerLatitude) &&
        !Number.isNaN(m.centerLongitude),
    )
    .map((m) => ({ lat: m.centerLatitude as number, lng: m.centerLongitude as number }));
  const userPts: LatLng[] = users.map((u) => ({ lat: u.latitude, lng: u.longitude }));
  const bounds = geoBounds([...userPts, ...marketCenters]);

  return (
    <div className={`${glass.card} p-4 space-y-3`}>
      <div>
        <h3 className={type.h2}>Where people are (profile GPS)</h3>
        <p className={`${type.caption} text-[var(--color-app-text-muted)] mt-1 max-w-[720px]`}>
          Each dot is the last location synced from the mobile app to <code className="text-[0.75rem]">profiles</code>.
          Rings are indexed market centers from inventory when coordinates exist. Markets can also be created from
          catalog venue cities without any user dot nearby—that is why the two layers do not always line up.
        </p>
      </div>
      <div
        className="relative w-full min-h-[min(52vw,320px)] max-h-[420px] rounded-[var(--radius-card)] border border-[var(--color-app-border)] bg-[var(--color-app-bg-elev)] overflow-hidden"
        role="img"
        aria-label="Scatter map of user locations and market centers"
      >
        {users.length === 0 && marketCenters.length === 0 ? (
          <div className="absolute inset-0 grid place-items-center p-6 text-center">
            <p className={`${type.body} text-[var(--color-app-text-muted)]`}>
              No coordinates yet. Open the app with location on so profiles pick up latitude and longitude, or import
              markets from the catalog so centers can appear.
            </p>
          </div>
        ) : null}
        {users.map((u) => {
          const pos = projectToPercent(u.latitude, u.longitude, bounds);
          return (
            <span
              key={u.userId}
              title={u.city ? `${u.city}` : u.userId.slice(0, 8)}
              className="absolute w-2.5 h-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-violet-bright)] shadow-[0_0_12px_rgba(167,139,250,0.55)]"
              style={{ left: pos.left, top: pos.top }}
            />
          );
        })}
        {markets.map((m) => {
          if (
            typeof m.centerLatitude !== 'number' ||
            typeof m.centerLongitude !== 'number' ||
            Number.isNaN(m.centerLatitude) ||
            Number.isNaN(m.centerLongitude)
          ) {
            return null;
          }
          const pos = projectToPercent(m.centerLatitude, m.centerLongitude, bounds);
          return (
            <span
              key={`m-${m.marketKey}`}
              title={`${m.city} (${m.marketKey})`}
              className="absolute w-4 h-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--color-success-neon)] bg-transparent opacity-90"
              style={{ left: pos.left, top: pos.top }}
            />
          );
        })}
      </div>
      <div className={`flex flex-wrap gap-4 ${type.caption} text-[var(--color-app-text-muted)]`}>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--color-violet-bright)]" /> User (profile)
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-full border-2 border-[var(--color-success-neon)]" /> Market
          center
        </span>
      </div>
    </div>
  );
}

// Marketing components extracted to ./marketing/MarketingHome.tsx

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
  const chipDate =
    'border-[color-mix(in_srgb,var(--color-app-mellow)_55%,transparent)] bg-[var(--color-app-mellow-muted)] text-[var(--color-app-mellow)]';
  const chipCategory =
    'border-[color-mix(in_srgb,var(--color-success-neon)_50%,transparent)] bg-[rgba(143,191,159,0.12)] text-[var(--color-success-neon)]';
  const chipVibe =
    'border-[color-mix(in_srgb,var(--color-app-clay)_55%,transparent)] bg-[var(--color-app-clay-muted)] text-[color-mix(in_srgb,var(--color-app-clay)_92%,white)]';
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
    'bg-[rgba(10,16,14,0.58)] border border-white/15 text-white hover:bg-[rgba(10,16,14,0.78)]';
  const violetTone = active
    ? 'bg-[var(--color-violet)] border border-[var(--color-violet-bright)] text-white shadow-[var(--glow-violet)]'
    : 'bg-[rgba(26,90,66,0.22)] border border-[var(--color-violet-bright)]/45 text-white hover:bg-[rgba(26,90,66,0.38)]';
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
  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: event.title,
          text: `Check out ${event.title} on Aventi!`,
          url: window.location.href,
        });
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          console.error('Error sharing:', err);
        }
      }
    } else {
      await navigator.clipboard.writeText(`${event.title} - ${window.location.href}`);
      alert('Event link copied to clipboard!');
    }
  };

  return (
    <article
      className={`relative h-[calc(100dvh-5.5rem)] [scroll-snap-align:start] overflow-hidden rounded-none md:rounded-[var(--radius-card)] md:h-auto md:min-h-[min(720px,calc(100dvh-9rem))] bg-[var(--color-app-bg-elev)] text-white ${motion.base} ${
        action === 'like'
          ? 'outline outline-[3px] outline-[var(--color-violet)] shadow-[var(--glow-violet)]'
          : ''
      }`}
    >
      <img src={event.imageUrl ?? heroImages[0]} alt="" className="object-cover absolute inset-0 w-full h-full" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(10,16,14,0.22),rgba(10,16,14,0.92)),linear-gradient(90deg,rgba(12,26,20,0.72),transparent_62%)]" />
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
        <PosterIconButton label="Share event" onClick={handleShare}>
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
    'border-[color-mix(in_srgb,var(--color-app-mellow)_55%,transparent)] bg-[var(--color-app-mellow-muted)] text-[var(--color-app-mellow)]';
  const chipVibe =
    'border-[color-mix(in_srgb,var(--color-app-clay)_55%,transparent)] bg-[var(--color-app-clay-muted)] text-[color-mix(in_srgb,var(--color-app-clay)_92%,white)]';

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
        className={`scrollbar-none fixed bottom-0 left-0 right-0 mx-auto md:max-w-[560px] md:bottom-6 z-50 max-h-[88dvh] md:max-h-[min(720px,calc(100dvh-64px))] overflow-y-auto rounded-t-[24px] md:rounded-[var(--radius-card)] border border-[var(--color-app-border)] md:border-t md:border bg-[color-mix(in_srgb,var(--color-app-bg-elev)_96%,transparent)] backdrop-blur-[18px] text-white shadow-[0_-30px_80px_rgba(0,0,0,0.5)] transition-[transform,opacity] duration-[var(--dur-base)] ease-[var(--ease-out)] ${
          open ? 'translate-y-0 opacity-100 pointer-events-auto' : 'translate-y-full opacity-0 pointer-events-none'
        }`}
      >
        {/* header — no “home indicator” drag pill; web filter panel is not a native sheet */}
        <div className="flex items-center justify-between px-5 pb-3 pt-4 border-b border-[var(--color-app-border)]">
          <div className="flex items-center gap-2">
            <span id="aventi-filters-title" className={type.h2}>Filters</span>
            {activeCount > 0 && (
              <span className="inline-grid place-items-center min-w-5 h-5 px-1.5 rounded-full bg-[var(--color-app-mellow-muted)] text-[var(--color-app-mellow)] border border-[color-mix(in_srgb,var(--color-app-mellow)_40%,transparent)] text-[0.7rem] font-bold">
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
                        ? 'border-[color-mix(in_srgb,var(--color-success-neon)_45%,transparent)] bg-[rgba(143,191,159,0.10)] shadow-[var(--glow-success)]'
                        : 'border-[var(--color-app-border)] bg-[var(--color-app-surface)]'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`inline-grid place-items-center w-9 h-9 rounded-[var(--radius-card)] ${
                          isActive
                            ? 'bg-[rgba(143,191,159,0.16)] text-[var(--color-success-neon)]'
                            : 'bg-[var(--color-app-surface-2)] text-[var(--color-app-text-muted)]'
                        }`}
                      >
                        {categoryIcons[category]}
                      </span>
                      <span className={`${type.body} font-semibold ${isActive ? 'text-[color-mix(in_srgb,var(--color-success-neon)_90%,white)]' : 'text-white'}`}>
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
                              ? 'bg-[rgba(143,191,159,0.12)] text-[var(--color-success-neon)]'
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
  const auth = useAuthSession();
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

  const feedMainRef = useRef<HTMLElement>(null);
  const feedEndLatchedRef = useRef(false);
  const [feedEndReached, setFeedEndReached] = useState(false);

  const updateFeedScrollEnd = useCallback(() => {
    const el = feedMainRef.current;
    if (!el || filteredEvents.length === 0) {
      feedEndLatchedRef.current = false;
      setFeedEndReached(false);
      return;
    }
    const { scrollTop, scrollHeight, clientHeight } = el;
    const nearBottom = scrollTop + clientHeight >= scrollHeight - 12;
    const cannotScroll = scrollHeight <= clientHeight + 8;
    const scrolledBackUp = scrollTop + clientHeight < scrollHeight - 160;
    if (nearBottom || cannotScroll) {
      feedEndLatchedRef.current = true;
      setFeedEndReached(true);
    } else if (scrolledBackUp && feedEndLatchedRef.current) {
      feedEndLatchedRef.current = false;
      setFeedEndReached(false);
    }
  }, [filteredEvents.length]);

  useEffect(() => {
    feedEndLatchedRef.current = false;
    setFeedEndReached(false);
  }, [filteredEvents]);

  useEffect(() => {
    const el = feedMainRef.current;
    if (!el) return;
    updateFeedScrollEnd();
    el.addEventListener('scroll', updateFeedScrollEnd, { passive: true });
    const ro = new ResizeObserver(() => updateFeedScrollEnd());
    ro.observe(el);
    return () => {
      el.removeEventListener('scroll', updateFeedScrollEnd);
      ro.disconnect();
    };
  }, [filteredEvents, updateFeedScrollEnd]);

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
      const params = new URLSearchParams(searchParams.toString());
      params.delete('filters');
      const newQuery = params.toString();
      router.replace(newQuery ? `${pathname}?${newQuery}` : pathname);
    }
  };

  return (
    <AppShell active={isFilterSheetOpen ? 'filters' : 'discovery'}>
      <section
        className="flex flex-1 min-h-0 flex-col px-3 sm:px-5 md:px-8 pt-4 md:pt-8 pb-0"
        id="feed"
      >
        {/* Top filter chip toolbar — desktop only, mobile uses the sheet */}
        <div className="hidden md:block mb-5 shrink-0">
          <FilterRail
            filters={filters}
            onToggleCategory={toggleCategory}
            onToggleVibe={toggleVibe}
            onSetDate={(date) => setFilters((current) => ({ ...current, date }))}
          />
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)] gap-5 overflow-hidden xl:grid-cols-[minmax(0,1fr)_340px] xl:grid-rows-1">
          <main
            ref={feedMainRef}
            className="scrollbar-none h-full min-h-0 overflow-y-auto overscroll-y-contain [scroll-snap-type:y_proximity] md:space-y-4 md:pr-1"
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
                <Sparkles size={28} className="text-[var(--color-app-mellow)]" />
                <h3 className={type.h1}>No matches</h3>
                <p className={type.caption}>
                  Aventi would trigger a targeted warming scan for this filter signature.
                </p>
                <Button variant="premium" size="md" onClick={refreshFeed}>
                  Mine more events
                </Button>
              </Surface>
            )}
            {feedEndReached && filteredEvents.length > 0 ? (
              <div className="mx-auto mt-4 max-w-lg scroll-mt-4 md:mt-6" role="status" aria-live="polite">
                <Surface className="mb-6 px-5 py-6 text-center">
                  <span className="mx-auto mb-3 inline-grid h-11 w-11 place-items-center rounded-full bg-[var(--color-app-mellow-muted)] text-[var(--color-app-mellow)]">
                    <Clock size={20} strokeWidth={1.6} aria-hidden />
                  </span>
                  <h3 className={type.h2}>You&apos;re caught up</h3>
                  <p className={`${type.body} mt-2 text-[var(--color-app-text-muted)]`}>
                    That&apos;s the end of this feed for now. Check back later for more events near you, or adjust
                    filters to widen what we show.
                  </p>
                </Surface>
              </div>
            ) : null}
          </main>

          <aside className={`hidden min-h-0 xl:block xl:sticky xl:top-[24px] xl:self-start ${glass.cardElev} p-5`}>
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
  const [activeTab, setActiveTab] = useState<'people' | 'markets' | 'scans'>('people');
  const [dashboard, setDashboard] = useState<AdminDashboardResponse | null>(null);
  const [userLocations, setUserLocations] = useState<AdminUserLocationPoint[] | null>(null);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [scanBusyKey, setScanBusyKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
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

  async function importMarketsFromCatalog() {
    const t = auth.session?.access_token ?? null;
    if (!t) return;
    setSyncBusy(true);
    setError(null);
    setActionError(null);
    try {
      await createAventiApi(t).postAdminImportMarketsFromCatalog();
      await loadDashboard(t);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to import markets from catalog');
    } finally {
      setSyncBusy(false);
    }
  }

  async function loadPeopleLocations() {
    const t = auth.session?.access_token ?? null;
    if (!t) return;
    setPeopleLoading(true);
    try {
      const res = await createAventiApi(t).getAdminUserLocations();
      setUserLocations(res.users);
    } catch {
      setUserLocations([]);
    } finally {
      setPeopleLoading(false);
    }
  }

  async function enqueueMarketScan(marketKey: string) {
    const t = auth.session?.access_token ?? null;
    if (!t) return;
    setScanBusyKey(marketKey);
    setActionError(null);
    try {
      await createAventiApi(t).postAdminEnqueueMarketScan({ marketKey });
      await loadDashboard(t);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to enqueue market scan');
    } finally {
      setScanBusyKey(null);
    }
  }

  useEffect(() => {
    if (auth.isReady && auth.session) {
      void loadDashboard(auth.session.access_token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.isReady]);

  useEffect(() => {
    if (activeTab !== 'people' || !auth.isReady || !auth.session?.access_token) return;
    void loadPeopleLocations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, auth.isReady, auth.session?.access_token]);

  const tabBtn = (tab: 'people' | 'markets' | 'scans') =>
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
        ? 'bg-[rgba(47,143,104,0.14)] text-[var(--color-violet-bright)] border-[var(--color-violet)]/40'
        : status === 'succeeded'
        ? 'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)] border-[var(--color-success-neon)]/40'
        : 'bg-[var(--color-app-surface)] text-[var(--color-app-text-muted)] border-[var(--color-app-border)]';
    return `inline-flex items-center px-2.5 h-6 rounded-full text-[0.7rem] font-semibold border ${tone}`;
  };

  return (
    <AppShell active="admin">
      <section
        className="scrollbar-none flex min-h-0 flex-1 flex-col overflow-y-auto px-4 sm:px-6 md:px-8 pt-6 md:pt-8 pb-12 max-w-[1100px] mx-auto w-full"
        id="admin"
      >
        <div className="max-w-[720px] mb-8">
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
            <div className="flex flex-wrap items-center gap-2 justify-end">
              <div
                className="flex items-center gap-1 p-1 rounded-full border border-[var(--color-app-border)] bg-[var(--color-app-surface)]"
                role="tablist"
                aria-label="Admin views"
              >
                <button className={tabBtn('people')} type="button" onClick={() => setActiveTab('people')}>
                  <Users size={14} strokeWidth={1.6} />
                  People
                </button>
                <button className={tabBtn('markets')} type="button" onClick={() => setActiveTab('markets')}>
                  <Gauge size={14} strokeWidth={1.6} />
                  Markets
                </button>
                <button className={tabBtn('scans')} type="button" onClick={() => setActiveTab('scans')}>
                  <Activity size={14} strokeWidth={1.6} />
                  Scans
                </button>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void importMarketsFromCatalog()}
                disabled={isLoading || syncBusy}
                title="Upsert market_inventory_state from venue cities on your event catalog (wide occurrence window), then recompute visible 7-day counts and heat tiers."
                leadingIcon={<Import size={14} strokeWidth={1.6} />}
              >
                Import catalog markets
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => loadDashboard()}
                disabled={isLoading || syncBusy}
                leadingIcon={<RefreshCcw size={14} strokeWidth={1.6} />}
              >
                Refresh
              </Button>
            </div>
          </div>

          {actionError ? (
            <p className={`${type.body} text-[var(--color-danger-glow)] mb-4`} role="alert">
              {actionError}
            </p>
          ) : null}

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

              {activeTab === 'people' ? (
                peopleLoading ? (
                  <Surface className="grid gap-3 place-items-center p-8 text-center mb-5">
                    <Loader2 size={24} className="animate-spin text-[var(--color-violet-bright)]" />
                    <p className={`${type.body} text-[var(--color-app-text-muted)]`}>Loading profile locations…</p>
                  </Surface>
                ) : (
                  <AdminPeopleMap users={userLocations ?? []} markets={dashboard.markets} />
                )
              ) : null}

              {activeTab === 'markets' && dashboard.markets.length === 0 ? (
                <p
                  className={`${type.body} text-[var(--color-app-text-muted)] mb-5 max-w-[560px]`}
                >
                  No markets are indexed yet. Rows are usually created when the mobile app reports
                  activity or a scan runs. If you already have events in Postgres, use{' '}
                  <strong className="text-[var(--color-app-text)]">Import catalog markets</strong> above
                  to backfill one row per venue city from the catalog.
                </p>
              ) : null}

              {activeTab === 'markets' ? (
                <>
                  {/* Desktop table — hidden on mobile */}
                  <div className={`${glass.card} overflow-x-auto hidden md:block`} role="table" aria-label="Market inventory state">
                    <div
                      className={`grid grid-cols-[1.25fr_0.95fr_0.55fr_0.95fr_0.95fr_0.55fr_auto] gap-3 min-w-[940px] px-4 py-3 items-center ${type.label} text-[var(--color-app-text-muted)]`}
                      role="row"
                    >
                      <span>Market</span>
                      <span>Status</span>
                      <span>Visible</span>
                      <span>Last scan</span>
                      <span>Targeted</span>
                      <span>Users</span>
                      <span className="text-right">Scan</span>
                    </div>
                    {dashboard.markets.map((market) => {
                      const status = marketStatus(market);
                      const queueOk = dashboard.workerQueue.configured;
                      return (
                        <div
                          className={`grid grid-cols-[1.25fr_0.95fr_0.55fr_0.95fr_0.95fr_0.55fr_auto] gap-3 min-w-[940px] px-4 py-3 items-center border-t border-[var(--color-app-border)] ${type.body}`}
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
                          <span className="flex justify-end">
                            <Button
                              variant="secondary"
                              size="sm"
                              type="button"
                              disabled={!queueOk || scanBusyKey === market.marketKey}
                              title={
                                queueOk
                                  ? 'Queue one short-window SerpAPI MARKET_SCAN for this city (requires worker + SQS).'
                                  : 'Configure SQS_WORKER_QUEUE_URL so jobs can be enqueued.'
                              }
                              leadingIcon={<Play size={12} strokeWidth={1.6} />}
                              onClick={() => void enqueueMarketScan(market.marketKey)}
                            >
                              {scanBusyKey === market.marketKey ? '…' : 'Queue'}
                            </Button>
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Mobile cards — visible below md */}
                  <div className="grid gap-3 md:hidden">
                    {dashboard.markets.map((market) => {
                      const status = marketStatus(market);
                      const queueOk = dashboard.workerQueue.configured;
                      return (
                        <article key={market.marketKey} className={`${glass.card} p-4 space-y-2`}>
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <strong className="block text-[var(--color-app-text)]">{market.city}</strong>
                              <small className={type.caption}>{market.heatTier} · {market.state ?? market.country}</small>
                            </div>
                            <span className={statusPill(status)}>{status.replace('_', ' ')}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[0.8rem]">
                            <span className="text-[var(--color-app-text-muted)]">Visible</span>
                            <span>{market.visibleEventCount7d}</span>
                            <span className="text-[var(--color-app-text-muted)]">Last scan</span>
                            <span>{formatDateTime(market.lastScanCompletedAt ?? market.lastScanStartedAt)}</span>
                            <span className="text-[var(--color-app-text-muted)]">Targeted</span>
                            <span>{formatDateTime(market.lastTargetedRequestedAt)}</span>
                            <span className="text-[var(--color-app-text-muted)]">Active users</span>
                            <span>{market.activeUserCount7d}</span>
                          </div>
                          <Button
                            variant="secondary"
                            size="sm"
                            type="button"
                            className="w-full mt-1"
                            disabled={!queueOk || scanBusyKey === market.marketKey}
                            title={
                              queueOk
                                ? 'Queue one short-window SerpAPI MARKET_SCAN for this city.'
                                : 'Configure SQS_WORKER_QUEUE_URL so jobs can be enqueued.'
                            }
                            leadingIcon={<Play size={12} strokeWidth={1.6} />}
                            onClick={() => void enqueueMarketScan(market.marketKey)}
                          >
                            {scanBusyKey === market.marketKey ? 'Queueing…' : 'Queue short scan'}
                          </Button>
                        </article>
                      );
                    })}
                  </div>
                </>
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


export function SavedPage() {
  // TODO(saved): Wire up to real persistence (Supabase favorites table).
  // Currently hardcoded empty — the empty-state UI is intentional.
  const savedEvents: EventCard[] = [];

  return (
    <AppShell active="saved">
      <div className="scrollbar-none mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col overflow-y-auto px-4 sm:px-6 pt-6 pb-12">
        <div className="flex items-center gap-3 mb-6">
          <h1 className={type.h1}>Saved events</h1>
          <Pill tone="violet">{savedEvents.length}</Pill>
        </div>

        {savedEvents.length === 0 ? (
          <Surface elev className="px-6 py-10 text-center grid place-items-center gap-4">
            <span className="w-14 h-14 rounded-full bg-[var(--color-app-mellow-muted)] text-[var(--color-app-mellow)] inline-grid place-items-center">
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
  // TODO(entitlements): Read premium status from auth session or a dedicated
  // entitlements hook once the membership backend is wired up.
  const isPremium = false;

  const displayName = useMemo(() => {
    if (!auth.email) return 'Guest Explorer';
    const local = auth.email.split('@')[0]?.replace(/[._-]+/g, ' ') ?? '';
    const titled = local.replace(/\b\w/g, (c) => c.toUpperCase());
    return titled || 'Aventi Explorer';
  }, [auth.email]);

  return (
    <AppShell active="profile">
      <div className="scrollbar-none mx-auto flex min-h-0 w-full max-w-[640px] flex-1 flex-col overflow-y-auto px-5 pt-10 pb-12">
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
              <span className="w-9 h-9 rounded-[var(--radius-card)] bg-[var(--color-app-mellow-muted)] text-[var(--color-app-mellow)] inline-grid place-items-center">
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
          href="/feed"
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
        <Button variant="destructive" size="md" fullWidth className="mt-5 !border-transparent" disabled title="Account deletion coming soon">
          Delete account
        </Button>
      </div>
      <AuthModal />
    </AppShell>
  );
}

// Re-export marketing home from its dedicated module.
export { MarketingHome } from './marketing/MarketingHome';

