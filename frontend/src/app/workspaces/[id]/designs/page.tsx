'use client';

/**
 * デザイン一覧ページ (BF プロジェクト内のデザイン画面リスト)
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
    Plus,
    Pencil,
    Trash2,
    ExternalLink,
    Loader2,
    LayoutGrid,
} from 'lucide-react';
import { designsApi, type DesignMock } from '@/lib/designs-api';

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
    draft: { label: '下書き', color: 'bg-gray-100 text-gray-700' },
    in_progress: { label: '進行中', color: 'bg-blue-100 text-blue-700' },
    review: { label: 'レビュー中', color: 'bg-amber-100 text-amber-700' },
    approved: { label: '承認済み', color: 'bg-emerald-100 text-emerald-700' },
    archived: { label: 'アーカイブ', color: 'bg-neutral-100 text-neutral-500' },
};

export default function DesignsListPage() {
    const params = useParams<{ id: string }>();
    const router = useRouter();
    const workspaceId = Number(params?.id ?? 0);

    const [designs, setDesigns] = useState<DesignMock[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showCreate, setShowCreate] = useState(false);
    const [creating, setCreating] = useState(false);

    const reload = useCallback(async () => {
        if (!workspaceId) return;
        try {
            setLoading(true);
            const list = await designsApi.list(workspaceId);
            setDesigns(list);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, [workspaceId]);

    useEffect(() => {
        reload();
    }, [reload]);

    const onDelete = async (id: number) => {
        if (!confirm('このデザインを削除しますか？(Penpot 上のファイルも削除されます)')) return;
        try {
            await designsApi.delete(workspaceId, id);
            await reload();
        } catch (e) {
            alert(`削除失敗: ${e instanceof Error ? e.message : e}`);
        }
    };

    return (
        <div className="p-6 max-w-6xl">
            {/* パンくず */}
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
                <Link href={`/workspaces/${workspaceId}`} className="hover:text-gray-900">
                    Workspace
                </Link>
                <span>/</span>
                <span className="text-gray-900 font-medium">デザイン</span>
            </div>

            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <LayoutGrid className="w-6 h-6" />
                        デザイン
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        プロジェクトに紐づく画面のデザインモック一覧。Penpot で編集・AI で生成可能。
                    </p>
                </div>
                <button
                    onClick={() => setShowCreate(true)}
                    className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                >
                    <Plus className="w-4 h-4" />
                    画面を追加
                </button>
            </div>

            {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 mb-4">
                    {error}
                </div>
            )}

            {loading ? (
                <div className="flex items-center gap-2 text-gray-500">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    読み込み中...
                </div>
            ) : designs.length === 0 ? (
                <div className="rounded-lg border-2 border-dashed border-gray-200 p-12 text-center">
                    <p className="text-gray-500 mb-4">まだデザインがありません</p>
                    <button
                        onClick={() => setShowCreate(true)}
                        className="text-emerald-600 hover:underline text-sm font-medium"
                    >
                        最初の画面を追加 →
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {designs.map((d) => (
                        <DesignCard
                            key={d.id}
                            design={d}
                            workspaceId={workspaceId}
                            onDelete={() => onDelete(d.id)}
                        />
                    ))}
                </div>
            )}

            {showCreate && (
                <CreateDialog
                    workspaceId={workspaceId}
                    onClose={() => setShowCreate(false)}
                    onCreated={async (created) => {
                        setShowCreate(false);
                        await reload();
                        // 作成直後に編集画面へ
                        router.push(`/workspaces/${workspaceId}/designs/${created.id}/editor`);
                    }}
                    creating={creating}
                    setCreating={setCreating}
                />
            )}
        </div>
    );
}

function DesignCard({
    design: d,
    workspaceId,
    onDelete,
}: {
    design: DesignMock;
    workspaceId: number;
    onDelete: () => void;
}) {
    const statusInfo = STATUS_LABEL[d.status] ?? STATUS_LABEL.draft;
    return (
        <div className="rounded-lg border bg-white overflow-hidden hover:shadow-md transition-shadow">
            {/* サムネイル領域 */}
            <Link
                href={`/workspaces/${workspaceId}/designs/${d.id}/editor`}
                className="block aspect-video bg-gradient-to-br from-gray-50 to-gray-100 border-b relative group"
            >
                {d.preview_image_url ? (
                    <img
                        src={d.preview_image_url}
                        alt={d.name}
                        className="w-full h-full object-cover"
                    />
                ) : (
                    <div className="absolute inset-0 flex items-center justify-center text-gray-300 text-xs">
                        プレビュー未生成
                    </div>
                )}
                <div className="absolute inset-0 bg-emerald-500/0 group-hover:bg-emerald-500/10 transition-colors flex items-center justify-center">
                    <span className="opacity-0 group-hover:opacity-100 bg-white/90 backdrop-blur rounded-full px-3 py-1.5 text-xs font-medium text-emerald-700 flex items-center gap-1.5 shadow-sm">
                        <Pencil className="w-3 h-3" />
                        編集する
                    </span>
                </div>
            </Link>

            <div className="p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                    <Link
                        href={`/workspaces/${workspaceId}/designs/${d.id}/editor`}
                        className="font-medium text-gray-900 hover:text-emerald-600 truncate flex-1"
                    >
                        {d.name}
                    </Link>
                    <span
                        className={`shrink-0 text-[10px] rounded-full px-2 py-0.5 font-medium ${statusInfo.color}`}
                    >
                        {statusInfo.label}
                    </span>
                </div>

                {d.route_path && (
                    <code className="text-[11px] text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded inline-block mb-2">
                        {d.route_path}
                    </code>
                )}

                {d.description && (
                    <p className="text-xs text-gray-600 line-clamp-2 mb-3">
                        {d.description}
                    </p>
                )}

                <div className="flex items-center justify-between pt-2 border-t">
                    <span className="text-[10px] text-gray-400">
                        {d.penpot_file_id ? `Penpot: ${d.penpot_file_id.slice(0, 8)}...` : 'Penpot 未連携'}
                    </span>
                    <div className="flex items-center gap-1">
                        <Link
                            href={`/workspaces/${workspaceId}/designs/${d.id}/editor`}
                            className="rounded p-1.5 text-gray-400 hover:bg-emerald-50 hover:text-emerald-600"
                            title="編集"
                        >
                            <Pencil className="w-3.5 h-3.5" />
                        </Link>
                        <button
                            onClick={onDelete}
                            className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600"
                            title="削除"
                        >
                            <Trash2 className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function CreateDialog({
    workspaceId,
    onClose,
    onCreated,
    creating,
    setCreating,
}: {
    workspaceId: number;
    onClose: () => void;
    onCreated: (d: DesignMock) => void;
    creating: boolean;
    setCreating: (v: boolean) => void;
}) {
    const [name, setName] = useState('');
    const [routePath, setRoutePath] = useState('');
    const [description, setDescription] = useState('');

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!name.trim()) return;
        setCreating(true);
        try {
            const created = await designsApi.create(workspaceId, {
                name: name.trim(),
                description: description.trim() || undefined,
                route_path: routePath.trim() || undefined,
            });
            onCreated(created);
        } catch (e) {
            alert(`作成失敗: ${e instanceof Error ? e.message : e}`);
            setCreating(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
            onMouseDown={onClose}
        >
            <form
                onSubmit={submit}
                onMouseDown={(e) => e.stopPropagation()}
                className="w-[460px] rounded-lg bg-white p-6 shadow-xl"
            >
                <h2 className="text-lg font-semibold mb-4">新しい画面デザイン</h2>

                <label className="block mb-3">
                    <span className="text-xs text-gray-600 mb-1 block">画面名 *</span>
                    <input
                        autoFocus
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="例: ログイン画面"
                        className="w-full rounded-md border px-3 py-2 text-sm focus:border-emerald-500 outline-none"
                    />
                </label>

                <label className="block mb-3">
                    <span className="text-xs text-gray-600 mb-1 block">ルート (任意)</span>
                    <input
                        type="text"
                        value={routePath}
                        onChange={(e) => setRoutePath(e.target.value)}
                        placeholder="/login"
                        className="w-full rounded-md border px-3 py-2 text-sm focus:border-emerald-500 outline-none font-mono"
                    />
                </label>

                <label className="block mb-5">
                    <span className="text-xs text-gray-600 mb-1 block">説明 (任意)</span>
                    <textarea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        rows={2}
                        placeholder="この画面の役割・主要要素など"
                        className="w-full rounded-md border px-3 py-2 text-sm focus:border-emerald-500 outline-none resize-none"
                    />
                </label>

                <div className="flex justify-end gap-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-md px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
                    >
                        キャンセル
                    </button>
                    <button
                        type="submit"
                        disabled={creating || !name.trim()}
                        className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1.5"
                    >
                        {creating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                        {creating ? '作成中...' : '作成 → 編集へ'}
                    </button>
                </div>
            </form>
        </div>
    );
}
