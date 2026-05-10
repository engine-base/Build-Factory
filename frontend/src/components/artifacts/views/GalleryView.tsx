"use client";

import { StarIcon } from "lucide-react";

interface GalleryItem {
  id: string;
  url: string;
  title?: string;
  caption?: string;
  favorite?: boolean;
}

interface Props {
  data: Record<string, unknown>;
  onChange?: (data: Record<string, unknown>) => void;
}

export function GalleryView({ data, onChange }: Props) {
  const items = Array.isArray(data.items) ? (data.items as GalleryItem[]) : [];

  const toggleFavorite = (id: string) => {
    const next = items.map((it) => it.id === id ? { ...it, favorite: !it.favorite } : it);
    onChange?.({ ...data, items: next });
  };

  if (items.length === 0) {
    return <div className="text-sm text-gray-500">画像/カードがありません</div>;
  }

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
      {items.map((it) => (
        <div key={it.id} className="group relative overflow-hidden rounded-lg border bg-white">
          <div className="aspect-square bg-gray-100">
            {it.url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={it.url}
                alt={it.title || ""}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-gray-400">
                画像 URL なし
              </div>
            )}
          </div>
          <button
            onClick={() => toggleFavorite(it.id)}
            className="absolute top-2 right-2"
            title="お気に入り"
          >
            <StarIcon
              className="w-5 h-5"
              fill={it.favorite ? "currentColor" : "none"}
              aria-label={it.favorite ? "favorite" : "not favorite"}
            />
          </button>
          {(it.title || it.caption) && (
            <div className="p-2">
              {it.title && <div className="text-xs font-semibold truncate">{it.title}</div>}
              {it.caption && <div className="text-[10px] text-gray-500 truncate">{it.caption}</div>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
