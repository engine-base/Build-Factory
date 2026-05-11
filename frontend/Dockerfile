# =============================================================================
# T-S0-01: Frontend Dockerfile (Next.js 16)
# =============================================================================
# Multi-stage build:
#   1. deps:    npm install (legacy peer deps)
#   2. build:   next build (production)
#   3. runtime: standalone Node 22 alpine + non-root
# =============================================================================

FROM node:22-alpine AS deps

WORKDIR /app

# package*.json のみコピーして依存だけインストール → cache 効率化
COPY package.json package-lock.json* ./

# legacy-peer-deps: React 19 + 一部 lib の peer 警告を許容
# ignore-scripts: postinstall scripts (free-email-domains 等) を skip
RUN npm install --legacy-peer-deps --ignore-scripts


FROM node:22-alpine AS build

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN npm run build


FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Next.js standalone output を最小限コピー
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
