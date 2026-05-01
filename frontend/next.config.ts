import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ─── Onlook self-host 時のリバースプロキシ ───────────────
  // Phase 1 (現状): onlook.com を別タブで開く運用なので無効
  // Phase 2 (self-host 移行時): 以下の rewrites を有効化して
  //   /design/* → http://localhost:3010/* にプロキシし
  //   1 アプリ感を出す
  //
  // async rewrites() {
  //   const onlookHost = process.env.ONLOOK_HOST || "http://localhost:3010";
  //   return [
  //     { source: "/design", destination: `${onlookHost}/` },
  //     { source: "/design/:path*", destination: `${onlookHost}/:path*` },
  //   ];
  // },
};

export default nextConfig;
