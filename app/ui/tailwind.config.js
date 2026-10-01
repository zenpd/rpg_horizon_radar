/** @type {import('tailwindcss').Config} */
// ZenLabs Agent Foundry design system (ported from digital-onboarding) so
// RPG Horizon Radar looks and feels like the rest of the org's agentic apps.
// The one deliberate addition is the `restricted` gradient/shadow pair,
// standing in for `gradient-zen` on this app's own primary actions and logo
// mark — a visual cue that this is the UPSI-adjacent, access-restricted app,
// not a generic product surface.
export default {
  // The radar screens (src/radar) use their own plain CSS; keep Tailwind out of them.
  content: ['./index.html', './src/**/*.{ts,tsx}', '!./src/radar/**'],
  // Preflight is applied scoped to .tw instead (src/tw-preflight.css), so it does not
  // reset the radar screens' styles.
  corePlugins: { preflight: false },
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        zen: {
          50: '#f0f4ff',
          100: '#e0eaff',
          200: '#c7d7fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,.06), 0 1px 2px -1px rgba(0,0,0,.06)',
        'card-hover': '0 8px 24px -4px rgba(79,70,229,.18), 0 2px 8px -2px rgba(0,0,0,.08)',
        sidebar: '1px 0 0 #e5e7eb',
        header: '0 1px 0 #e5e7eb',
        'glow-zen': '0 0 16px 2px rgba(99,102,241,.35)',
        'glow-restricted': '0 0 16px 2px rgba(190,18,60,.35)',
        'glow-emerald': '0 0 12px 2px rgba(16,185,129,.30)',
        'glow-amber': '0 0 12px 2px rgba(245,158,11,.30)',
        'inner-top': 'inset 0 1px 0 rgba(255,255,255,.12)',
      },
      backgroundImage: {
        'gradient-zen': 'linear-gradient(135deg, #6366f1 0%, #4f46e5 50%, #4338ca 100%)',
        'gradient-zen-soft': 'linear-gradient(135deg, #f0f4ff 0%, #e0eaff 100%)',
        'gradient-restricted': 'linear-gradient(135deg, #e11d48 0%, #be123c 60%, #9f1239 100%)',
        'gradient-restricted-soft': 'linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%)',
        shimmer: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,.6) 50%, transparent 100%)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.25s ease-out',
        'slide-in-right': 'slideInRight 0.3s cubic-bezier(.16,1,.3,1)',
        'slide-in-left': 'slideInLeft 0.3s cubic-bezier(.16,1,.3,1)',
        'pulse-dot': 'pulseDot 1.5s ease-in-out infinite',
        'pulse-ring': 'pulseRing 2s ease-out infinite',
        shimmer: 'shimmer 2s ease-in-out infinite',
        'bounce-sm': 'bounceSm 1s ease-in-out infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        slideInRight: { from: { opacity: 0, transform: 'translateX(16px)' }, to: { opacity: 1, transform: 'translateX(0)' } },
        slideInLeft: { from: { opacity: 0, transform: 'translateX(-16px)' }, to: { opacity: 1, transform: 'translateX(0)' } },
        pulseDot: { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.4 } },
        pulseRing: { '0%': { transform: 'scale(.9)', opacity: .7 }, '70%': { transform: 'scale(1.4)', opacity: 0 }, '100%': { transform: 'scale(.9)', opacity: 0 } },
        shimmer: { '0%': { backgroundPosition: '-400px 0' }, '100%': { backgroundPosition: '400px 0' } },
        bounceSm: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-3px)' } },
      },
    },
  },
  plugins: [],
}
