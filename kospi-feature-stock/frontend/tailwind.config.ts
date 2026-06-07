import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 다크 팔레트
        dark: {
          bg:     '#09090b',
          card:   '#18181b',
          border: '#27272a',
          muted:  '#71717a',
          fg:     '#fafafa',
        },
        // 라이트 팔레트
        light: {
          bg:     '#f4f4f5',
          card:   '#ffffff',
          border: '#e4e4e7',
          muted:  '#71717a',
          fg:     '#09090b',
        },
        brand: {
          cyan:   '#22d3ee',
          green:  '#4ade80',
          red:    '#f87171',
          yellow: '#fbbf24',
          blue:   '#60a5fa',
          purple: '#a78bfa',
        },
        // HTS 전용
        hts: {
          up:   '#f04040',
          dn:   '#4488ff',
          flat: '#71717a',
        },
      },
      fontFamily: {
        mono: ["'SF Mono'", "'Fira Code'", 'Menlo', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', "'Segoe UI'", "'Noto Sans KR'", 'sans-serif'],
      },
      animation: {
        blink:     'blink 2s ease-in-out infinite',
        spin:      'spin 0.65s linear infinite',
        toastIn:   'toastIn 0.2s ease',
        flashUp:   'flashUp 0.4s ease-out both',
        flashDn:   'flashDn 0.4s ease-out both',
        fadeHighlight: 'fadeHighlight 1.5s ease',
      },
      keyframes: {
        blink:          { '0%,100%': { opacity: '1' }, '50%': { opacity: '.35' } },
        toastIn:        { from: { transform: 'translateX(110%)', opacity: '0' }, to: { transform: 'translateX(0)', opacity: '1' } },
        flashUp:        { '0%': { background: 'rgba(240,64,64,.32)' }, '100%': { background: 'transparent' } },
        flashDn:        { '0%': { background: 'rgba(68,136,255,.32)' }, '100%': { background: 'transparent' } },
        fadeHighlight:  { from: { background: 'rgba(34,211,238,.08)' }, to: { background: 'transparent' } },
      },
    },
  },
  plugins: [],
} satisfies Config
