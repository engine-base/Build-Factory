// Stub for @/env. Build-Factory exposes only NEXT_PUBLIC_API_URL today.
export const env = {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001',
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3001',
} as Record<string, string>;
