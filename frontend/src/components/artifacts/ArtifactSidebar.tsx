"use client";

import { useEffect, useState } from "react";
import {
  PinIcon,
  ArchiveIcon,
  CheckCircle2Icon,
  FolderIcon,
  ClipboardListIcon,
  BarChart3Icon,
  FileTextIcon,
  TrendingUpIcon,
  CalendarIcon,
  ScaleIcon,
  RepeatIcon,
  ImageIcon,
  TargetIcon,
  PencilIcon,
  FilmIcon,
  BrainIcon,
} from "lucide-react";
import {
  Artifact,
  ArtifactWS,
  CategorySummary,
  fetchArtifacts,
  fetchCategorySummary,
  unpinArtifact,
} from "@/lib/artifacts";

interface Props {
  onSelect?: (artifact: Artifact) => void;
}

/**
 * 既存の左メニュー（dashboard / employee 等）に**追加配置**するセクション。
 * トップにピン留め、その下にカテゴリ別件数。
 */
export function ArtifactSidebar({ onSelect }: Props) {
  const [pinned, setPinned] = useState<Artifact[]>([]);
  const [categories, setCategories] = useState<CategorySummary[]>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [categoryItems, setCategoryItems] = useState<Artifact[]>([]);

  const reloadPinned = async () => {
    const { artifacts } = await fetchArtifacts({ pinned_only: true, limit: 30 });
    setPinned(artifacts);
  };

  const reloadCategories = async () => {
    setCategories(await fetchCategorySummary());
  };

  useEffect(() => {
    reloadPinned();
    reloadCategories();

    const ws = new ArtifactWS("masato");
    ws.connect();
    const off = ws.on(() => {
      reloadPinned();
      reloadCategories();
      if (activeCategory) loadCategory(activeCategory);
    });
    return () => {
      off();
      ws.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadCategory = async (key: string) => {
    setActiveCategory(key);
    const { artifacts } = await fetchArtifacts({ category: key, limit: 50 });
    setCategoryItems(artifacts);
  };

  return (
    <div className="space-y-4 p-3">
      {/* ピン留めセクション */}
      <div>
        <div className="mb-1.5 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
          <span className="inline-flex items-center gap-1">
            <PinIcon className="w-3.5 h-3.5" aria-hidden="true" />
            ピン留め
          </span>
          <span className="text-gray-400">{pinned.length}</span>
        </div>
        <ul className="space-y-0.5">
          {pinned.length === 0 && (
            <li className="px-2 text-xs text-gray-400">なし</li>
          )}
          {pinned.map((a) => (
            <li key={a.id} className="group flex items-center gap-2 rounded px-2 py-1 hover:bg-gray-100">
              <button
                onClick={() => onSelect?.(a)}
                className="flex-1 inline-flex items-center gap-1 truncate text-left text-sm"
                title={a.title}
              >
                <TypeIcon type={a.type} className="w-3.5 h-3.5" />
                <span className="truncate">{a.title || a.type}</span>
              </button>
              <button
                onClick={async () => {
                  await unpinArtifact(a.id);
                  reloadPinned();
                }}
                className="invisible text-xs text-gray-400 group-hover:visible hover:text-red-500"
                title="ピン解除"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* カテゴリ */}
      <div>
        <div className="mb-1.5 inline-flex items-center gap-1 px-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
          <ArchiveIcon className="w-3.5 h-3.5" aria-hidden="true" />
          ライブラリ
        </div>
        <ul className="space-y-0.5">
          {categories.map((c) => (
            <li key={c.key}>
              <button
                onClick={() => loadCategory(c.key)}
                className={`flex w-full items-center justify-between rounded px-2 py-1 text-sm hover:bg-gray-100 ${
                  activeCategory === c.key ? "bg-gray-100 font-medium" : ""
                }`}
              >
                <span>{c.label}</span>
                <span className="text-xs text-gray-500">{c.count}</span>
              </button>
            </li>
          ))}
        </ul>

        {activeCategory && (
          <ul className="mt-2 space-y-0.5 border-l pl-3">
            {categoryItems.length === 0 && (
              <li className="text-xs text-gray-400">空</li>
            )}
            {categoryItems.map((a) => (
              <li key={a.id}>
                <button
                  onClick={() => onSelect?.(a)}
                  className="inline-flex w-full items-center gap-1 truncate rounded px-2 py-1 text-left text-xs hover:bg-gray-100"
                  title={a.title}
                >
                  <TypeIcon type={a.type} className="w-3 h-3" />
                  <span className="truncate">{a.title || a.type}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TypeIcon({ type, className }: { type: string; className?: string }) {
  const cls = className ?? "w-3.5 h-3.5";
  switch (type) {
    case "list":
      return <CheckCircle2Icon className={cls} aria-hidden="true" />;
    case "kanban":
      return <FolderIcon className={cls} aria-hidden="true" />;
    case "table":
      return <ClipboardListIcon className={cls} aria-hidden="true" />;
    case "kpi-card":
      return <BarChart3Icon className={cls} aria-hidden="true" />;
    case "markdown":
      return <FileTextIcon className={cls} aria-hidden="true" />;
    case "chart":
      return <TrendingUpIcon className={cls} aria-hidden="true" />;
    case "gantt":
      return <CalendarIcon className={cls} aria-hidden="true" />;
    case "calendar":
      return <CalendarIcon className={cls} aria-hidden="true" />;
    case "compare":
      return <ScaleIcon className={cls} aria-hidden="true" />;
    case "workflow":
      return <RepeatIcon className={cls} aria-hidden="true" />;
    case "gallery":
      return <ImageIcon className={cls} aria-hidden="true" />;
    case "matrix":
      return <TargetIcon className={cls} aria-hidden="true" />;
    case "form":
      return <PencilIcon className={cls} aria-hidden="true" />;
    case "slide":
      return <FilmIcon className={cls} aria-hidden="true" />;
    case "mindmap":
      return <BrainIcon className={cls} aria-hidden="true" />;
    default:
      return <span className={cls} aria-hidden="true">•</span>;
  }
}
