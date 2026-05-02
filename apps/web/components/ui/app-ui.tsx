'use client';

import type { ButtonHTMLAttributes, AnchorHTMLAttributes, ReactNode } from 'react';

/**
 * App-surface design system primitives.
 * Use across the dark immersive surfaces (/feed, /profile, /saved, /filters, /discovery, /admin).
 * Marketing site (/) keeps its own light brand styling.
 */

// Type scale — Poppins, sentence case throughout. Use these classNames directly.
export const type = {
  display: 'text-[2rem] leading-[2.25rem] font-extrabold tracking-[-0.01em]',
  h1: 'text-[1.5rem] leading-[1.875rem] font-extrabold tracking-[-0.005em]',
  h2: 'text-[1.125rem] leading-[1.5rem] font-bold',
  body: 'text-[0.9375rem] leading-[1.375rem] font-medium',
  caption: 'text-[0.8125rem] leading-[1.125rem] font-medium text-[var(--color-app-text-muted)]',
  // Small label slot — tab labels, plan pills, toggle groups. Sentence case.
  label: 'text-[0.75rem] leading-[1rem] font-semibold tracking-[0.01em]',
} as const;

// Glass surface class strings.
export const glass = {
  card:
    'rounded-[var(--radius-card)] border border-[var(--color-app-border)] bg-[var(--color-app-surface)] backdrop-blur-[14px]',
  cardElev:
    'rounded-[var(--radius-card)] border border-[var(--color-app-border)] bg-[var(--color-app-surface-2)] backdrop-blur-[14px] shadow-[0_30px_80px_rgba(0,0,0,0.35)]',
  bar:
    'border border-[var(--color-app-border)] bg-[rgba(7,7,13,0.78)] backdrop-blur-[18px]',
};

// Motion class string — apply on any interactive surface.
export const motion = {
  base: 'transition-[background-color,border-color,color,opacity,transform,box-shadow] duration-[var(--dur-base)] ease-[var(--ease-out)]',
  fast: 'transition-[background-color,border-color,color,opacity,transform] duration-[var(--dur-fast)] ease-[var(--ease-out)]',
};

// ── Button ────────────────────────────────────────────────────────────────

type ButtonVariant = 'primary' | 'premium' | 'secondary' | 'ghost' | 'destructive';
type ButtonSize = 'sm' | 'md' | 'lg';

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-9 px-3 text-[0.8125rem]',
  md: 'h-11 px-4 text-[0.9375rem]',
  lg: 'h-14 px-5 text-[1rem]',
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-[var(--color-violet)] text-white hover:bg-[var(--color-violet-bright)] active:scale-[0.98] shadow-[var(--glow-violet)]',
  premium:
    'text-white active:scale-[0.98] shadow-[var(--glow-violet)] [background:var(--gradient-premium)] hover:brightness-110',
  secondary:
    'bg-[var(--color-app-surface)] text-[var(--color-app-text)] border border-[var(--color-app-border)] hover:bg-[var(--color-app-surface-2)] active:scale-[0.98]',
  ghost:
    'bg-transparent text-[var(--color-app-text-muted)] hover:bg-[var(--color-app-surface)] hover:text-[var(--color-app-text)]',
  destructive:
    'bg-transparent text-[var(--color-danger-glow)] border border-[var(--color-danger-glow)]/40 hover:bg-[var(--color-danger-glow)]/10 hover:shadow-[var(--glow-danger)] hover:border-[var(--color-danger-glow)]/70',
};

const buttonBase =
  'inline-flex items-center justify-center gap-2 rounded-[var(--radius-card)] font-semibold whitespace-nowrap select-none disabled:opacity-50 disabled:pointer-events-none';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  leadingIcon,
  trailingIcon,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      className={`${buttonBase} ${motion.base} ${sizeClasses[size]} ${variantClasses[variant]} ${
        fullWidth ? 'w-full' : ''
      } ${className}`}
    >
      {leadingIcon}
      {children}
      {trailingIcon}
    </button>
  );
}

// Anchor variant — same look, renders as <a>.
interface ButtonLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

export function ButtonLink({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  leadingIcon,
  trailingIcon,
  className = '',
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <a
      {...rest}
      className={`${buttonBase} ${motion.base} ${sizeClasses[size]} ${variantClasses[variant]} ${
        fullWidth ? 'w-full' : ''
      } ${className}`}
    >
      {leadingIcon}
      {children}
      {trailingIcon}
    </a>
  );
}

// ── Surface ──────────────────────────────────────────────────────────────

interface SurfaceProps {
  elev?: boolean;
  children: ReactNode;
  className?: string;
}

export function Surface({ elev = false, children, className = '' }: SurfaceProps) {
  return (
    <div className={`${elev ? glass.cardElev : glass.card} ${className}`}>
      {children}
    </div>
  );
}

// ── Pill ─────────────────────────────────────────────────────────────────

interface PillProps {
  children: ReactNode;
  tone?: 'neutral' | 'violet' | 'success' | 'danger' | 'premium';
  className?: string;
}

const pillTones: Record<NonNullable<PillProps['tone']>, string> = {
  neutral:
    'bg-[var(--color-app-surface)] text-[var(--color-app-text-muted)] border border-[var(--color-app-border)]',
  violet:
    'bg-[rgba(107,75,255,0.14)] text-[var(--color-violet-bright)] border border-[rgba(107,75,255,0.28)]',
  success:
    'bg-[rgba(77,255,168,0.10)] text-[var(--color-success-neon)] border border-[rgba(77,255,168,0.28)] shadow-[var(--glow-success)]',
  danger:
    'bg-[rgba(255,77,109,0.10)] text-[var(--color-danger-glow)] border border-[rgba(255,77,109,0.30)]',
  premium:
    'text-white border-0 [background:var(--gradient-premium)]',
};

export function Pill({ tone = 'neutral', children, className = '' }: PillProps) {
  return (
    <span
      className={`inline-flex items-center px-3 h-7 rounded-full ${type.label} ${pillTones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
