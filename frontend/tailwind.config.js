/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        fg: 'var(--color-text)',
        muted: 'var(--color-text-secondary)',
        line: 'var(--color-border)',
        sidebar: '#111111',
        'sidebar-hover': '#1F1F1F',
        'sidebar-active': '#262626',
        ok: '#16A34A',
        warn: '#D97706',
        crit: '#DC2626',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
      },
      fontSize: {
        '2xs': ['11px', '16px'],
      },
      borderRadius: {
        DEFAULT: '4px',
        md: '6px',
      },
      maxWidth: {
        content: '1400px',
      },
    },
  },
  plugins: [],
}
