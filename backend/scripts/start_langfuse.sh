#!/usr/bin/env bash
# Langfuse を Docker Compose で起動するスクリプト
# Usage: bash scripts/start_langfuse.sh

set -euo pipefail

LANGFUSE_DIR="${HOME}/Documents/Build-Factory/data/langfuse"
mkdir -p "${LANGFUSE_DIR}"
cd "${LANGFUSE_DIR}"

if [ ! -f docker-compose.yml ]; then
  cat > docker-compose.yml <<'YAML'
services:
  langfuse-db:
    image: postgres:16
    restart: always
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
    volumes:
      - langfuse_db_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"

  langfuse:
    image: langfuse/langfuse:2
    restart: always
    depends_on:
      - langfuse-db
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: change-me-please
      SALT: change-me-please
      ENCRYPTION_KEY: 0000000000000000000000000000000000000000000000000000000000000000
      NEXTAUTH_URL: http://localhost:3000
      TELEMETRY_ENABLED: "false"

volumes:
  langfuse_db_data:
YAML
  echo "[+] docker-compose.yml を生成: ${LANGFUSE_DIR}/docker-compose.yml"
fi

docker compose up -d

echo ""
echo "[✓] Langfuse 起動完了"
echo "  URL: http://localhost:3000"
echo "  初回はサインアップしてプロジェクト作成 → API Keys からキー取得"
echo "  取得した PUBLIC_KEY / SECRET_KEY を backend/.env に設定:"
echo "    LANGFUSE_PUBLIC_KEY=..."
echo "    LANGFUSE_SECRET_KEY=..."
echo "    LANGFUSE_HOST=http://localhost:3000"
