"use client";

import Link from "next/link";
import {
  ChevronRight, Search, Bell, CircleHelp,
} from "lucide-react";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface Props {
  breadcrumbs?: BreadcrumbItem[];
  showSearch?: boolean;
  unread?: boolean;
}

export function WorkspaceHeader({
  breadcrumbs = [], showSearch = true, unread = true,
}: Props) {
  return (
    <header
      className="flex items-center"
      style={{
        height: "var(--bf-header-h)",
        padding: "0 var(--bf-space-6)",
        background: "var(--bf-bg-elev)",
        borderBottom: "1px solid var(--bf-border)",
        gap: "var(--bf-space-6)",
      }}
    >
      <Link href="/" className="flex items-center gap-2" style={{
        fontWeight: 700, color: "var(--bf-text-1)",
        letterSpacing: "-0.01em", fontSize: 15,
      }}>
        <div
          style={{
            width: 24, height: 24,
            background: "var(--bf-primary)",
            borderRadius: "var(--bf-radius-sm)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#fff", fontWeight: 700, fontSize: 13,
            letterSpacing: "-0.02em",
          }}
        >
          BF
        </div>
        Build-Factory
      </Link>

      {breadcrumbs.length > 0 && (
        <>
          <div style={{ width: 1, height: 20, background: "var(--bf-border)" }} />
          <nav className="flex items-center gap-2" style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
            {breadcrumbs.map((b, i) => {
              const last = i === breadcrumbs.length - 1;
              return (
                <span key={i} className="flex items-center gap-2">
                  {b.href && !last ? (
                    <Link href={b.href} className="hover:text-[var(--bf-text-1)]">
                      {b.label}
                    </Link>
                  ) : (
                    <span style={{ color: last ? "var(--bf-text-1)" : undefined, fontWeight: last ? 500 : undefined }}>
                      {b.label}
                    </span>
                  )}
                  {!last && <ChevronRight className="w-3.5 h-3.5" />}
                </span>
              );
            })}
          </nav>
        </>
      )}

      <div className="flex-1" />

      {showSearch && (
        <button
          className="flex items-center gap-2 transition-colors"
          style={{
            background: "var(--bf-bg-soft)",
            border: "1px solid var(--bf-border)",
            borderRadius: "var(--bf-radius-md)",
            padding: "6px 10px",
            color: "var(--bf-text-3)",
            width: 280,
            fontSize: 13,
          }}
        >
          <Search className="w-3.5 h-3.5" />
          検索 / コマンドパレット
          <span
            className="ml-auto"
            style={{
              fontSize: 11,
              color: "var(--bf-text-4)",
              background: "var(--bf-bg-elev)",
              border: "1px solid var(--bf-border)",
              borderRadius: 4,
              padding: "1px 5px",
            }}
          >
            ⌘K
          </span>
        </button>
      )}

      <div className="flex items-center gap-3">
        <HeaderIconBtn dot={unread}>
          <Bell className="w-[18px] h-[18px]" />
        </HeaderIconBtn>
        <HeaderIconBtn>
          <CircleHelp className="w-[18px] h-[18px]" />
        </HeaderIconBtn>
        <div
          style={{
            width: 28, height: 28, borderRadius: "50%",
            background: "linear-gradient(135deg, #2563EB, #06B6D4)",
            color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontWeight: 600, fontSize: 11,
          }}
        >
          MA
        </div>
      </div>
    </header>
  );
}

function HeaderIconBtn({ children, dot }: { children: React.ReactNode; dot?: boolean }) {
  return (
    <button
      className="relative flex items-center justify-center transition-colors"
      style={{
        width: 32, height: 32,
        borderRadius: "var(--bf-radius-md)",
        color: "var(--bf-text-3)",
      }}
    >
      {children}
      {dot && (
        <span
          aria-hidden
          style={{
            position: "absolute", top: 4, right: 4,
            width: 6, height: 6,
            background: "var(--bf-danger)",
            borderRadius: "50%",
          }}
        />
      )}
    </button>
  );
}
