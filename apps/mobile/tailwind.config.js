const { nativeWindThemeExtend } = require('../../packages/design-tokens/nativewind-theme.cjs');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: nativeWindThemeExtend,
  },
  plugins: [],
};
