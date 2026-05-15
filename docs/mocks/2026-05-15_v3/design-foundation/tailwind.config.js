/** @type {import('tailwindcss').Config} */
// Build-Factory v3 — design-foundation 出力
// 参照: docs/mocks/2026-05-15_v3/design-foundation/tokens.json
// 既存実装統合先: frontend/tailwind.config.ts (= 等価書き換え可能)

module.exports = {
  darkMode: ['class'],
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // ===== Base color scales (具体スケール / 直接参照可) =====
        slate: {
          50:  '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
          400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#334155',
          800: '#1e293b', 900: '#0f172a', 950: '#020617',
        },
        eb: {
          50:  '#f0faf5', 100: '#d3f0e0', 200: '#a8e1c1', 300: '#6dcc94',
          400: '#34b164', 500: '#1a6648', 600: '#155238', 700: '#103e2a',
          800: '#0c2e1f', 900: '#082015', 950: '#04110a',
        },

        // ===== Semantic tokens (shadcn 流 HSL CSS 変数経由) =====
        // CSS は app/globals.css で :root と .dark に展開
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        // Build-Factory 独自 (両 mode 共通の濃グリーン sidebar)
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar))',
          foreground: 'hsl(var(--sidebar-foreground))',
        },
        // 状態色 (Tailwind 公式色を直接参照)
        success: '#16a34a',
        warning: '#d97706',
        info: '#2563eb',
      },
      borderRadius: {
        xl: '12px',       // Modal / Dialog
        lg: '8px',        // Card
        md: '6px',        // Button / Input
        sm: '4px',
      },
      fontFamily: {
        sans: ['"Noto Sans JP"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        // 既定 Tailwind より圧縮されたスケール
        // 'text-2xl' = 24px (h1), 'text-lg' = 18px (h2), 'text-base' = 16px, 'text-sm' = 14px
        // KPI hero などは text-[28px] でインライン指定
      },
      lineHeight: {
        japanese: '1.7',
      },
      letterSpacing: {
        widest: '0.05em',
      },
      maxWidth: {
        container: '1400px',
        sidebar: '240px',
      },
      spacing: {
        sidebar: '240px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(0,0,0,0.04)',
        md: '0 2px 8px rgba(0,0,0,0.06)',
        lg: '0 4px 12px rgba(0,0,0,0.10)',
        xl: '0 12px 32px rgba(0,0,0,0.12)',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 1.4s infinite',
      },
      screens: {
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
      },
    },
  },
  plugins: [
    require('tailwindcss-animate'),
  ],
};
