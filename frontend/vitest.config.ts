/**
 * Vitest configuration for Build-Factory frontend (T-V3-C-TEST-01).
 *
 * Coverage gate (Phase 1): branches/functions/lines/statements >= 70%.
 * Test scope: frontend/tests/**\/*.spec.{ts,tsx} (54 screen specs at infra landing).
 *
 * NOTE: Wave 0 only lands the infra. The 54 spec files still carry
 *       `// @ts-nocheck` and remain skipped by default via a deliberate
 *       include pattern; representative specs are exercised by removing
 *       the marker on a per-file basis in this PR.
 */
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.spec.{ts,tsx}"],
    exclude: [
      "node_modules/**",
      ".next/**",
      "e2e/**",
      "__tests__/**",
      "tests/**/*.skip.{ts,tsx}",
    ],
    css: false,
    pool: "forks",
    poolOptions: {
      forks: {
        singleFork: true,
      },
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov", "json-summary"],
      reportsDirectory: "./coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.d.ts",
        "src/**/*.stories.{ts,tsx}",
        "src/**/__mocks__/**",
        "src/env.ts",
        "src/middleware.ts",
      ],
      thresholds: {
        branches: 70,
        functions: 70,
        lines: 70,
        statements: 70,
      },
    },
  },
});
