"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle, XCircle, Wifi, Mail, MessageSquare, RefreshCw } from "lucide-react";

const API = "http://localhost:8001";

type ChannelStatus = {
  slack: { connected: boolean; bot_user_id?: string; team?: string; error?: string };
  gmail: { connected: boolean; email?: string; error?: string };
  scheduler: { running: boolean; job_count: number };
};

const CHANNEL_INFO = [
  {
    key: "slack" as const,
    label: "Slack",
    description: "承認通知・完了通知・コマンド受付",
    icon: MessageSquare,
    color: "#4A154B",
    bg: "#F4EFF4",
  },
  {
    key: "gmail" as const,
    label: "Gmail",
    description: "受信トレイ監視・メール送信",
    icon: Mail,
    color: "#D44638",
    bg: "#FEF2F2",
  },
];

export default function ChannelsPage() {
  const { data: status, isLoading, refetch, isFetching } = useQuery<ChannelStatus>({
    queryKey: ["channels-status"],
    queryFn: () => fetch(`${API}/api/channels/status`).then(r => r.json()),
    refetchInterval: 30000,
  });

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>チャンネル設定</h1>
        <button onClick={() => refetch()}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-opacity hover:opacity-80"
          style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
          <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
          更新
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--eb-neutral)" }}>
          <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          読み込み中...
        </div>
      ) : (
        <div className="space-y-4">
          {CHANNEL_INFO.map(({ key, label, description, icon: Icon, color, bg }) => {
            const ch = status?.[key];
            const connected = ch?.connected ?? false;
            return (
              <div key={key} className="rounded-xl p-6 bg-white"
                style={{ border: "1px solid var(--eb-border)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                    style={{ background: bg }}>
                    <Icon className="w-5 h-5" style={{ color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h2 className="font-bold text-sm" style={{ fontFamily: "var(--font-inter)" }}>{label}</h2>
                      <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full"
                        style={{
                          background: connected ? "#DCFCE7" : "#FEE2E2",
                          color: connected ? "#16A34A" : "#DC2626",
                          fontFamily: "var(--font-inter)"
                        }}>
                        {connected
                          ? <><CheckCircle className="w-2.5 h-2.5" /> 接続中</>
                          : <><XCircle className="w-2.5 h-2.5" /> 未接続</>}
                      </span>
                    </div>
                    <p className="text-xs mb-3" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                      {description}
                    </p>

                    {connected && (
                      <div className="space-y-1 text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                        {key === "slack" && status?.slack && (
                          <>
                            {status.slack.team && (
                              <div className="flex gap-2">
                                <span className="w-20 shrink-0">ワークスペース</span>
                                <span className="font-medium text-gray-700">{status.slack.team}</span>
                              </div>
                            )}
                            {status.slack.bot_user_id && (
                              <div className="flex gap-2">
                                <span className="w-20 shrink-0">Bot ID</span>
                                <span className="font-medium text-gray-700">{status.slack.bot_user_id}</span>
                              </div>
                            )}
                          </>
                        )}
                        {key === "gmail" && status?.gmail?.email && (
                          <div className="flex gap-2">
                            <span className="w-20 shrink-0">アカウント</span>
                            <span className="font-medium text-gray-700">{status.gmail.email}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {!connected && ch?.error && (
                      <p className="text-xs p-2 rounded"
                        style={{ background: "#FEE2E2", color: "#991B1B", fontFamily: "var(--font-inter)" }}>
                        {ch.error}
                      </p>
                    )}

                    {!connected && !ch?.error && (
                      <p className="text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                        {key === "slack"
                          ? "SLACK_BOT_TOKEN と SLACK_APP_TOKEN を .env に設定してください"
                          : "Gmail OAuth2 認証を完了してください（python gmail_client.py auth）"}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Scheduler status */}
          <div className="rounded-xl p-6 bg-white" style={{ border: "1px solid var(--eb-border)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: "#EFF6FF" }}>
                <Wifi className="w-5 h-5" style={{ color: "var(--eb-primary)" }} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="font-bold text-sm" style={{ fontFamily: "var(--font-inter)" }}>スケジューラー</h2>
                  <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full"
                    style={{
                      background: status?.scheduler?.running ? "#DCFCE7" : "#FEE2E2",
                      color: status?.scheduler?.running ? "#16A34A" : "#DC2626",
                      fontFamily: "var(--font-inter)"
                    }}>
                    {status?.scheduler?.running
                      ? <><CheckCircle className="w-2.5 h-2.5" /> 稼働中</>
                      : <><XCircle className="w-2.5 h-2.5" /> 停止中</>}
                  </span>
                </div>
                <p className="text-xs mb-3" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                  定期実行ジョブ管理（ブリーフィング・受信トレイチェック等）
                </p>
                {status?.scheduler && (
                  <p className="text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    登録ジョブ数: <span className="font-semibold text-gray-700">{status.scheduler.job_count}件</span>
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Guide */}
      <div className="mt-8 p-5 rounded-xl" style={{ background: "var(--eb-surface-variant)", border: "1px solid var(--eb-border)" }}>
        <h3 className="text-xs font-bold mb-3" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>Slackコマンド一覧</h3>
        <div className="space-y-1.5 text-xs" style={{ fontFamily: "var(--font-inter)", color: "var(--eb-neutral)" }}>
          {[
            ["承認 N", "ID番号Nの項目を承認"],
            ["却下 N", "ID番号Nの項目を却下"],
            ["修正 N: テキスト", "ID番号Nへ修正指示"],
            ["承認一覧", "承認待ち一覧を表示"],
          ].map(([cmd, desc]) => (
            <div key={cmd} className="flex gap-4">
              <code className="w-32 shrink-0 text-gray-700 font-mono">{cmd}</code>
              <span>{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
