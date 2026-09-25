/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0a0f1a',
          900: '#0e1526',
          800: '#141d33',
          700: '#1b2740',
          600: '#26324d',
          500: '#3a4966',
        },
        accent: {
          DEFAULT: '#b8862e',
          light: '#d4a44f',
          dark: '#8f6a22',
        },
        severity: {
          low: '#1f8a5f',
          mid: '#b8862e',
          high: '#b0362c',
        },
      },
      fontFamily: {
        sans: ["'Inter'", 'system-ui', 'sans-serif'],
        mono: ["'JetBrains Mono'", 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}
