export const aventiColors = {
  canvas: '#000000',
  ink: '#F9FAFB',
  muted: '#9CA3AF',
  border: 'rgba(255,255,255,0.14)',
  glass: 'rgba(255,255,255,0.08)',
  overlay: 'rgba(0,0,0,0.72)',
} as const;

export const categoryGradients = {
  nightlife: ['#7C3AED', '#312E81'],
  dining: ['#F97316', '#B91C1C'],
  concerts: ['#D946EF', '#FB7185'],
  wellness: ['#14B8A6', '#06B6D4'],
  experiences: ['#0EA5E9', '#1E3A8A'],
} as const;

export const spacing = {
  cardRadius: 28,
  buttonSize: 60,
  screenGutter: 20,
} as const;

export const typography = {
  heroTitle: {
    letterSpacing: 2,
    textTransform: 'uppercase' as const,
  },
};

export const nativeWindThemeExtend = {
  colors: {
    aventi: {
      canvas: aventiColors.canvas,
      ink: aventiColors.ink,
      muted: aventiColors.muted,
      border: aventiColors.border,
      glass: aventiColors.glass,
      overlay: aventiColors.overlay,
    },
    nightlife: {
      500: categoryGradients.nightlife[0],
      700: categoryGradients.nightlife[1],
    },
    dining: {
      500: categoryGradients.dining[0],
      700: categoryGradients.dining[1],
    },
    concerts: {
      500: categoryGradients.concerts[0],
      700: categoryGradients.concerts[1],
    },
    wellness: {
      500: categoryGradients.wellness[0],
      700: categoryGradients.wellness[1],
    },
  },
  borderRadius: {
    'aventi-card': `${spacing.cardRadius}px`,
  },
} as const;
