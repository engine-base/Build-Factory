"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, MessageSquare, FileText, Users, TrendingUp,
  Bot, CheckSquare, BookOpen, ScrollText, Wifi, Cpu, FolderOpen, ListTodo, Sparkles, Package, LayoutGrid,
  Building2,
} from "lucide-react";

const AI_NAV = [
  { href: "/workspaces",   label: "🏗 Workspaces",   icon: LayoutGrid },
  { href: "/secretary",    label: "秘書チャット",     icon: Sparkles },
  { href: "/ai-employees", label: "AI社員",           icon: Bot },
  { href: "/artifacts",    label: "Artifacts",        icon: Package },
  { href: "/tasks",        label: "タスク管理",       icon: ListTodo },
  { href: "/approval",     label: "承認待ち",         icon: CheckSquare, badge: true },
  { href: "/skills",       label: "スキル管理",       icon: Cpu },
  { href: "/knowledge",    label: "ナレッジ",         icon: BookOpen },
  { href: "/documents",    label: "資料・添付",       icon: FolderOpen },
  { href: "/logs",         label: "実行ログ",         icon: ScrollText },
  { href: "/channels",     label: "チャンネル",       icon: Wifi },
  { href: "/settings/account", label: "会社設定",     icon: Building2 },
  { href: "/settings/references", label: "参考資料",   icon: FileText },
];


export function Sidebar() {
  const pathname = usePathname();

  // 全 hooks を先に呼ぶ (React rules of hooks: 条件で hook をスキップしない)
  const { data: pendingCount = 0 } = useQuery({
    queryKey: ["approval-count"],
    queryFn: async () => {
      const res = await fetch("http://localhost:8001/api/approval?status=pending");
      if (!res.ok) return 0;
      const data = await res.json();
      return Array.isArray(data) ? data.length : 0;
    },
    refetchInterval: 15000,
  });

  // 全 hooks を呼んだあとで非表示判定 (React rules of hooks 違反を回避)
  // /workspaces/[id]/designs/[did]/editor は Penpot iframe の全画面 UI を出すため Sidebar 非表示
  const isFullscreenEditor =
    !!pathname &&
    /^\/workspaces\/\d+\/designs\/\d+\/editor(\/|$)/.test(pathname);
  // /workspaces/[id] 配下は WorkspaceShell が独自サイドバーを持つためアカウントサイドバー非表示
  const isInsideWorkspace =
    !!pathname && /^\/workspaces\/\d+(\/|$)/.test(pathname);
  if (isFullscreenEditor || isInsideWorkspace) {
    return null;
  }

  return (
    <aside
      className="w-56 h-screen flex flex-col shrink-0"
      style={{ background: "var(--eb-primary)", color: "#fff" }}
    >
      {/* ブランド */}
      <div
        className="flex items-center gap-2.5 px-4 h-14 shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.12)" }}
      >
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "rgba(255,255,255,0.15)" }}
        >
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="min-w-0">
          <p className="font-bold text-xs tracking-tight leading-tight text-white">ENGINE BASE</p>
          <p className="text-[9px] leading-tight" style={{ color: "rgba(255,255,255,0.5)", letterSpacing: "0.06em" }}>
            AI社員システム
          </p>
        </div>
      </div>

      {/* ナビゲーション */}
      <nav className="flex-1 p-2 overflow-y-auto">
        <p className="px-2 pt-2 pb-1 text-[9px] font-bold uppercase tracking-widest"
          style={{ color: "rgba(255,255,255,0.4)" }}>AI社員</p>

        {AI_NAV.map(({ href, label, icon: Icon, badge }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link key={href} href={href}
              className="flex items-center gap-2 px-2 py-2 rounded-md text-xs mb-0.5 transition-colors"
              style={{
                background: active ? "rgba(255,255,255,0.14)" : "transparent",
                color: active ? "#fff" : "rgba(255,255,255,0.72)",
                fontWeight: active ? 600 : 400,
              }}
            >
              <Icon className="w-3.5 h-3.5 shrink-0" />
              <span className="flex-1 truncate">{label}</span>
              {badge && pendingCount > 0 && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0"
                  style={{ background: "var(--eb-tertiary)", color: "#fff", minWidth: 18, textAlign: "center" }}>
                  {pendingCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-3 text-[9px]"
        style={{ borderTop: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.35)" }}>
        <p>株式会社ENGINE BASE</p>
        <p style={{ fontFamily: "var(--font-inter)" }}>AI社員システム v1.0</p>
      </div>
    </aside>
  );
}
