export const aventiPalette = {
  forest: '#032F25',
  pine: '#214437',
  sage: '#9AAA8F',
  moss: '#B8BA96',
  sand: '#EDE3D1',
  clay: '#B94A31',
  mellow: '#E3AD43',
  ocean: '#164A57',
  charcoal: '#1F211F',
  cream: '#F5F0E7',
  white: '#FFFFFF',
} as const;

export const aventiColors = {
  canvas: aventiPalette.forest,
  canvasRaised: '#08392E',
  canvasElevated: aventiPalette.pine,
  paper: aventiPalette.cream,
  sand: aventiPalette.sand,
  ink: aventiPalette.white,
  inkDark: aventiPalette.charcoal,
  inkSoft: 'rgba(245,240,231,0.86)',
  muted: 'rgba(245,240,231,0.62)',
  forest: aventiPalette.forest,
  pine: aventiPalette.pine,
  sage: aventiPalette.sage,
  moss: aventiPalette.moss,
  clay: aventiPalette.clay,
  mellow: aventiPalette.mellow,
  ocean: aventiPalette.ocean,
  charcoal: aventiPalette.charcoal,
  accent: aventiPalette.mellow,
  warm: aventiPalette.clay,
  cool: aventiPalette.ocean,
  border: 'rgba(245,240,231,0.14)',
  borderStrong: 'rgba(245,240,231,0.24)',
  glass: 'rgba(245,240,231,0.07)',
  glassStrong: 'rgba(245,240,231,0.12)',
  overlay: 'rgba(3,47,37,0.78)',
  // Back-compat aliases. Visual mapping follows current moodboard.
  violet: aventiPalette.forest,
  pink: aventiPalette.mellow,
  orange: aventiPalette.clay,
  cyan: aventiPalette.ocean,
  green: aventiPalette.pine,
} as const;

export const aventiGradients = {
  primary: [aventiPalette.forest, aventiPalette.pine, aventiPalette.mellow],
  warm: [aventiPalette.clay, aventiPalette.mellow],
  calm: [aventiPalette.forest, aventiPalette.ocean],
  paper: [aventiPalette.cream, aventiPalette.sand],
  success: [aventiPalette.sage, aventiPalette.pine],
  surfaceGlow: ['rgba(227,173,67,0.18)', 'rgba(185,74,49,0.12)', 'rgba(245,240,231,0.08)'],
  // Back-compat aliases.
  nightlife: [aventiPalette.forest, aventiPalette.clay],
  sunset: [aventiPalette.clay, aventiPalette.mellow],
  electric: [aventiPalette.ocean, aventiPalette.sage],
} as const;

export const categoryGradients = {
  nightlife: [aventiPalette.forest, aventiPalette.clay],
  dining: [aventiPalette.clay, aventiPalette.mellow],
  concerts: [aventiPalette.charcoal, aventiPalette.clay],
  wellness: [aventiPalette.pine, aventiPalette.sage],
  experiences: [aventiPalette.ocean, aventiPalette.sage],
  comedy: [aventiPalette.mellow, aventiPalette.clay],
  sports: [aventiPalette.pine, aventiPalette.moss],
  outdoors: [aventiPalette.forest, aventiPalette.sage],
  markets: [aventiPalette.mellow, aventiPalette.pine],
  tech: [aventiPalette.ocean, aventiPalette.charcoal],
} as const;

export const spacing = {
  cardRadius: 22,
  sheetRadius: 28,
  buttonSize: 56,
  screenGutter: 20,
  touchTarget: 44,
} as const;

export const typography = {
  heroTitle: {
    letterSpacing: 0,
    fontFamily: 'Poppins_700Bold',
  },
  title: {
    letterSpacing: 0,
    fontFamily: 'Poppins_600SemiBold',
  },
  label: {
    letterSpacing: 1.6,
    textTransform: 'uppercase' as const,
  },
} as const;

export const motion = {
  fast: 160,
  standard: 240,
  deliberate: 300,
} as const;

export const nativeWindThemeExtend = {
  colors: {
    aventi: {
      canvas: aventiColors.canvas,
      raised: aventiColors.canvasRaised,
      elevated: aventiColors.canvasElevated,
      paper: aventiColors.paper,
      sand: aventiColors.sand,
      ink: aventiColors.ink,
      inkDark: aventiColors.inkDark,
      inkSoft: aventiColors.inkSoft,
      muted: aventiColors.muted,
      forest: aventiColors.forest,
      pine: aventiColors.pine,
      sage: aventiColors.sage,
      moss: aventiColors.moss,
      clay: aventiColors.clay,
      mellow: aventiColors.mellow,
      ocean: aventiColors.ocean,
      charcoal: aventiColors.charcoal,
      accent: aventiColors.accent,
      warm: aventiColors.warm,
      cool: aventiColors.cool,
      violet: aventiColors.violet,
      pink: aventiColors.pink,
      orange: aventiColors.orange,
      cyan: aventiColors.cyan,
      green: aventiColors.green,
      border: aventiColors.border,
      borderStrong: aventiColors.borderStrong,
      glass: aventiColors.glass,
      glassStrong: aventiColors.glassStrong,
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
    'aventi-sheet': `${spacing.sheetRadius}px`,
  },
} as const;
