// TODO: Build-Factory integration - replace with proper design tokens
// Minimal token surface used by design-canvas overlay
type ColorScale = Record<string, string>;

const scale = (base: string, mid: string): ColorScale => ({
    50: mid, 100: mid, 200: mid, 300: mid, 400: mid,
    500: base, 600: base, 700: base, 800: base, 900: base,
});

export const colors = {
    blue: scale('#2563eb', '#dbeafe'),
    red: scale('#dc2626', '#fee2e2'),
    green: scale('#22c55e', '#dcfce7'),
    yellow: scale('#eab308', '#fef9c3'),
    orange: scale('#ea580c', '#ffedd5'),
    purple: scale('#9333ea', '#f3e8ff'),
    pink: scale('#db2777', '#fce7f3'),
    teal: scale('#0d9488', '#ccfbf1'),
    cyan: scale('#0891b2', '#cffafe'),
    indigo: scale('#4f46e5', '#e0e7ff'),
    gray: scale('#6b7280', '#f3f4f6'),
    slate: scale('#475569', '#f1f5f9'),
    white: '#ffffff',
    black: '#000000',
} as const;
