import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Phase 1: iframe は直接 PENPOT_PUBLIC_URL (http://localhost:9001) を読み込む。
  // 初回のみ Penpot にログインしてもらう (Phase 2 で OIDC SSO 実装後は完全 auto)。
  // proxy 経由は Penpot 内部 routing が壊れるため不採用。
};

export default nextConfig;
