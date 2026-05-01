'use client';

import { useParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { Suspense } from 'react';

// Onlook 由来の Canvas は client only + mobx 依存のため動的 import
const DesignCanvas = dynamic(
    () => import('@/components/design-canvas/canvas').then((m) => m.Canvas),
    {
        ssr: false,
        loading: () => (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
                キャンバスを読み込み中...
            </div>
        ),
    },
);

const EditorEngineProvider = dynamic(
    () =>
        import('@/components/design-canvas/store').then(
            (m) => m.EditorEngineProvider,
        ),
    { ssr: false },
);

export default function WorkspaceDesignPage() {
    const params = useParams<{ id: string }>();
    const workspaceId = params?.id ?? '';

    return (
        <div className="flex h-screen w-screen flex-col bg-neutral-950 text-neutral-100">
            {/* ── ヘッダー ───────────────────────────── */}
            <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 px-4">
                <div className="flex items-center gap-3">
                    <Link
                        href={`/workspaces/${workspaceId}`}
                        className="text-sm text-neutral-300 hover:text-white"
                    >
                        ← Workspace
                    </Link>
                    <span className="text-neutral-600">/</span>
                    <h1 className="text-sm font-medium">デザインキャンバス</h1>
                    <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">
                        ベータ
                    </span>
                </div>
                <div className="flex items-center gap-2 text-xs text-neutral-400">
                    <span>workspace_id: {workspaceId}</span>
                </div>
            </header>

            {/* ── キャンバス本体 ──────────────────────── */}
            <main className="relative flex-1 overflow-hidden">
                <Suspense fallback={null}>
                    <EditorEngineProvider projectId={`ws-${workspaceId}`}>
                        <DesignCanvas />
                    </EditorEngineProvider>
                </Suspense>
            </main>

            {/* ── ステータスバー ─────────────────────── */}
            <footer className="flex h-7 shrink-0 items-center justify-between border-t border-white/10 px-4 text-[11px] text-neutral-500">
                <span>Onlook canvas (Apache-2.0) 統合済</span>
                <span>EditorEngine: stub mode (REST 配線は次フェーズ)</span>
            </footer>
        </div>
    );
}
