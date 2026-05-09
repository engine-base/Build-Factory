/**
 * AI 大分類リーダーのアバター。1 文字 + カラー識別 + 角丸 4px。
 * 絵文字は使わない（Calm Industrial 規約）。
 */
import type { LeaderId } from "./types";

const LEADER_COLOR: Record<LeaderId, string> = {
  secretary: "var(--bf-leader-secretary)",
  pm:        "var(--bf-leader-pm)",
  arch:      "var(--bf-leader-arch)",
  design:    "var(--bf-leader-design)",
  eng:       "var(--bf-leader-eng)",
  qa:        "var(--bf-leader-qa)",
  ops:       "var(--bf-leader-ops)",
};

const LEADER_SHORT: Record<LeaderId, string> = {
  secretary: "秘",
  pm:        "PM",
  arch:      "設",
  design:    "デ",
  eng:       "エ",
  qa:        "品",
  ops:       "運",
};

export function LeaderAvatar({
  id, size = 22, className,
}: {
  id: LeaderId;
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        borderRadius: "var(--bf-radius-sm)",
        background: LEADER_COLOR[id],
        color: "#fff",
        fontWeight: 700,
        fontSize: Math.max(9, Math.round(size * 0.45)),
        letterSpacing: "0.02em",
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      {LEADER_SHORT[id]}
    </span>
  );
}
