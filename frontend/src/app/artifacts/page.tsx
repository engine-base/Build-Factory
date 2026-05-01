"use client";

import { useState } from "react";
import { Artifact } from "@/lib/artifacts";
import { ArtifactPanel } from "@/components/artifacts/ArtifactPanel";
import { ArtifactSidebar } from "@/components/artifacts/ArtifactSidebar";

/**
 * /artifacts — 専用管理ビュー
 *  ・左: ピン留め + カテゴリ
 *  ・右: 選択した artifact の詳細 / 編集
 */
export default function ArtifactsPage() {
  const [selected, setSelected] = useState<Artifact | null>(null);

  return (
    <div className="flex h-full">
      <aside className="w-72 shrink-0 border-r bg-white overflow-y-auto">
        <div className="border-b px-4 py-3">
          <h1 className="font-bold text-sm">📦 Artifacts</h1>
          <p className="text-[10px] text-gray-500 mt-0.5">
            出力・成果物のライブラリ
          </p>
        </div>
        <ArtifactSidebar onSelect={setSelected} />
      </aside>

      <div className="flex-1 overflow-hidden">
        {selected ? (
          <ArtifactPanel
            key={selected.id}
            threadId={selected.thread_id ?? undefined}
          />
        ) : (
          <ArtifactPanel />
        )}
      </div>
    </div>
  );
}
