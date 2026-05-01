"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { ArtifactPanel } from "@/components/artifacts/ArtifactPanel";
import { Package } from "lucide-react";

const API = "http://localhost:8001";

type Employee = {
  id: number;
  persona_name: string | null;
  display_name: string;
  avatar_emoji: string | null;
};

export default function SecretaryPage() {
  const { data: secretary } = useQuery<Employee>({
    queryKey: ["secretary-persona"],
    queryFn: () => fetch(`${API}/api/staff/1`).then(r => r.json()).catch(() => null),
  });

  const avatar = secretary?.avatar_emoji || "🎀";
  const name = secretary?.persona_name || "秘書";

  const [showArtifacts, setShowArtifacts] = useState(false);

  return (
    <div className="flex h-full">
      {/* チャット（既存無改造）*/}
      <div className="flex-1 min-w-0">
        <ChatPanel
          mode="secretary"
          employeeColor="#7E3AED"
          avatarEmoji={avatar}
          headerExtra={
            <div className="px-4 py-3 bg-white flex items-center gap-3"
              style={{ borderBottom: "1px solid var(--eb-border)" }}>
              <div className="w-9 h-9 rounded-full flex items-center justify-center text-xl"
                style={{ background: "#7E3AED22" }}>{avatar}</div>
              <div className="flex-1">
                <h1 className="font-bold text-sm" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                  秘書 {name}
                </h1>
                <p className="text-[10px]" style={{ color: "var(--eb-neutral)" }}>
                  深掘り・タスク分解・社員割当を自動で行います
                </p>
              </div>
              <button
                onClick={() => setShowArtifacts((v) => !v)}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs transition ${
                  showArtifacts
                    ? "bg-blue-500 text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
                title="Artifact パネルを開閉"
              >
                <Package className="w-3.5 h-3.5" />
                Artifacts
              </button>
            </div>
          }
        />
      </div>

      {/* 右パネル: 必要時だけ表示 */}
      {showArtifacts && (
        <aside className="w-[460px] shrink-0">
          <ArtifactPanel onClose={() => setShowArtifacts(false)} />
        </aside>
      )}
    </div>
  );
}
