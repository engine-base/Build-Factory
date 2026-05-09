'use client';

/**
 * デザイン編集ページ — Penpot を iframe で BF 内に表示。
 * URL: /workspaces/:wid/designs/:did/editor
 *
 * ユーザー視点では「BF 内のデザイン編集画面」。
 * 中身は Penpot だが BF のヘッダー (戻る・画面名) で囲まれている。
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
    ChevronLeft,
    Loader2,
    ExternalLink,
    Save,
    Sparkles,
} from 'lucide-react';
import { designsApi, type DesignMock } from '@/lib/designs-api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

export default function DesignEditorPage() {
    const params = useParams<{ id: string; designId: string }>();
    const router = useRouter();
    const workspaceId = Number(params?.id ?? 0);
    const designId = Number(params?.designId ?? 0);

    const [design, setDesign] = useState<DesignMock | null>(null);
    const [embedUrl, setEmbedUrl] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [authenticated, setAuthenticated] = useState(false);

    const reload = useCallback(async () => {
        if (!workspaceId || !designId) return;
        try {
            setLoading(true);
            setError(null);

            // 1) design が存在するか先に確認 (404 ならエラー UI)
            let d: DesignMock;
            try {
                d = await designsApi.get(workspaceId, designId);
            } catch (e) {
                const msg = e instanceof Error ? e.message : String(e);
                if (msg.includes('404')) {
                    setError(
                        'このデザインは見つかりません。削除されたか URL が間違っている可能性があります。',
                    );
                    setLoading(false);
                    return;
                }
                throw e;
            }
            setDesign(d);
            setAuthenticated(true);

            // 2) embed URL を取得 (Penpot 直接 URL)
            const embed = await designsApi
                .embedUrl(workspaceId, designId)
                .catch(() => null);
            if (embed?.embed_url) {
                setEmbedUrl(embed.embed_url);
            } else {
                setError(
                    'Penpot ファイルが見つかりません。デザインを再作成してください。',
                );
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, [workspaceId, designId]);

    useEffect(() => {
        reload();
    }, [reload]);

    return (
        <div className="flex h-screen w-full flex-col bg-gray-50">
            {/* BF ヘッダー */}
            <header className="flex h-12 shrink-0 items-center justify-between border-b bg-white px-4 z-10">
                <div className="flex items-center gap-3">
                    <Link
                        href={`/workspaces/${workspaceId}/designs`}
                        className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
                    >
                        <ChevronLeft className="w-4 h-4" />
                        デザイン一覧
                    </Link>
                    <span className="text-gray-300">/</span>
                    <h1 className="text-sm font-medium text-gray-900">
                        {design?.name || (loading ? '読み込み中...' : '画面名')}
                    </h1>
                    {design?.status && (
                        <span className="text-[10px] rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">
                            {design.status}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        disabled
                        title="Phase 3 で実装"
                        className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs text-gray-400 cursor-not-allowed"
                    >
                        <Sparkles className="w-3.5 h-3.5" />
                        AI で生成
                    </button>
                    <button
                        type="button"
                        disabled
                        title="Phase 4 で実装"
                        className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs text-gray-400 cursor-not-allowed"
                    >
                        <Save className="w-3.5 h-3.5" />
                        BF に同期
                    </button>
                </div>
            </header>

            {/* iframe area */}
            <main className="relative flex-1 overflow-hidden">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
                        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                    </div>
                )}
                {error && (
                    <div className="absolute inset-0 flex items-center justify-center bg-white">
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center max-w-md">
                            <p className="text-sm text-amber-800 mb-4">{error}</p>
                            <div className="flex gap-2 justify-center">
                                <Link
                                    href={`/workspaces/${workspaceId}/designs`}
                                    className="rounded-md bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-700"
                                >
                                    デザイン一覧へ戻る
                                </Link>
                                <button
                                    onClick={reload}
                                    className="rounded-md border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
                                >
                                    再試行
                                </button>
                            </div>
                        </div>
                    </div>
                )}
                {embedUrl && (
                    <iframe
                        src={embedUrl}
                        title={design?.name || 'Design Editor'}
                        className="w-full h-full border-0"
                        allow="clipboard-read; clipboard-write; fullscreen"
                        onLoad={(e) => {
                            // 同一オリジンなので iframe.contentDocument にアクセスして CSS 注入。
                            // Penpot のロゴ・ヘッダー・ダッシュボードリンク等を Build-Factory 風に隠す。
                            try {
                                const doc = (e.currentTarget as HTMLIFrameElement)
                                    .contentDocument;
                                if (!doc) return;
                                const style = doc.createElement('style');
                                style.id = '__bf_penpot_overrides';
                                style.textContent = `
/* Build-Factory: Penpot のブランド要素を隠す */
.main_logo, .penpot-logo,
[class*="logo_penpot"],
[class*="brand-logo"],
.dashboard_topbar a[href="/"],
.workspace-topbar .logo-section,
.main-logo-section { display: none !important; }
/* Penpot ダッシュボード内のフッター・ヘルプリンク類も簡素化 */
.dashboard-help-button { display: none !important; }
                                `;
                                if (!doc.getElementById('__bf_penpot_overrides')) {
                                    doc.head.appendChild(style);
                                }
                            } catch (err) {
                                console.warn('[design] iframe CSS inject failed:', err);
                            }
                        }}
                    />
                )}
                {!loading && !embedUrl && !error && (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-gray-400">
                            <p className="text-sm mb-2">編集 URL を取得できませんでした</p>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
