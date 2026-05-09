"use client";

import { useCallback, useRef, useState, useEffect } from "react";
import { Upload, Crop as CropIcon, Trash2, Image as ImageIcon, Loader2 } from "lucide-react";
import { uploadImage } from "@/lib/account-settings-api";

interface Props {
  label: string;
  hint?: string;
  accountId: number;
  kind: "logo" | "stamp" | "ceo_photo" | "case_study" | "hero_bg" | "icon" | "other";
  value?: string;
  onChange: (url: string) => void;
  /** crop モード ('square' | 'free' | 'none') */
  cropMode?: "square" | "free" | "none";
  /** プレビュー高さ */
  previewHeight?: number;
}

export function ImageDropper({
  label, hint, accountId, kind, value, onChange,
  cropMode = "square", previewHeight = 120,
}: Props) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (file: File) => {
    setError(null);
    if (!file.type.startsWith("image/")) {
      setError("画像ファイルを選択してください");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setError("ファイルサイズは 15MB 以下にしてください");
      return;
    }
    if (cropMode === "none") {
      doUpload(file);
    } else {
      setPendingFile(file);  // open crop modal
    }
  };

  const doUpload = async (file: Blob, filename = "upload.png") => {
    setBusy(true);
    setError(null);
    try {
      const result = await uploadImage({ accountId, kind, file, filename });
      onChange(result.url);
    } catch (e: any) {
      setError(e?.message || "アップロード失敗");
    } finally {
      setBusy(false);
      setPendingFile(null);
    }
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDrag(true);
  }, []);

  const onDragLeave = useCallback(() => setDrag(false), []);

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  const clear = () => onChange("");

  return (
    <div>
      <label style={{ fontSize: 11.5, fontWeight: 700, color: "var(--bf-text-3)", letterSpacing: "0.04em", display: "block", marginBottom: 6 }}>
        {label}
      </label>

      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${drag ? "var(--bf-primary)" : "var(--bf-border)"}`,
          background: drag ? "var(--bf-primary-bg)" : value ? "var(--bf-bg)" : "var(--bf-bg)",
          borderRadius: 10,
          padding: 14,
          cursor: "pointer",
          transition: "all 150ms",
          minHeight: previewHeight + 24,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
        }}
      >
        {value ? (
          <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={value.startsWith("http") || value.startsWith("/") ? value : `http://localhost:8001${value}`}
              alt={label}
              style={{ maxHeight: previewHeight, maxWidth: "100%", borderRadius: 6, objectFit: "contain" }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
                style={{ padding: "4px 10px", fontSize: 11, fontWeight: 600, color: "var(--bf-primary)", background: "transparent", border: "1px solid var(--bf-primary)", borderRadius: 6, cursor: "pointer" }}
              >
                <Upload className="w-3 h-3 inline mr-1" />差替え
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); clear(); }}
                style={{ padding: "4px 10px", fontSize: 11, fontWeight: 600, color: "var(--bf-danger)", background: "transparent", border: "1px solid var(--bf-danger)", borderRadius: 6, cursor: "pointer" }}
              >
                <Trash2 className="w-3 h-3 inline mr-1" />削除
              </button>
            </div>
          </div>
        ) : busy ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--bf-primary)" }} />
            <div style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>アップロード中…</div>
          </>
        ) : (
          <>
            <ImageIcon className="w-7 h-7" style={{ color: "var(--bf-text-4)" }} />
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--bf-text-2)" }}>
              ここにドラッグ または クリックして選択
            </div>
            {hint && <div style={{ fontSize: 11, color: "var(--bf-text-4)" }}>{hint}</div>}
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onPickFile}
        style={{ display: "none" }}
      />

      {error && (
        <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--bf-danger)" }}>{error}</div>
      )}

      {pendingFile && (
        <CropModal
          file={pendingFile}
          mode={cropMode === "free" ? "free" : "square"}
          onCancel={() => setPendingFile(null)}
          onConfirm={(blob) => doUpload(blob, pendingFile.name)}
        />
      )}
    </div>
  );
}

/* ──────── Crop Modal (シンプル square crop) ──────── */
function CropModal({
  file, mode, onCancel, onConfirm,
}: {
  file: File;
  mode: "square" | "free";
  onCancel: () => void;
  onConfirm: (blob: Blob) => void;
}) {
  const [imgUrl, setImgUrl] = useState<string>("");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0, size: 0 });
  const [imgSize, setImgSize] = useState({ w: 0, h: 0 });
  const [drag, setDrag] = useState<{ startX: number; startY: number; cx: number; cy: number } | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setImgUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const onImgLoad = () => {
    const img = imgRef.current;
    if (!img) return;
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    setImgSize({ w, h });
    const size = Math.min(w, h);
    setCrop({
      x: Math.max(0, (w - size) / 2),
      y: Math.max(0, (h - size) / 2),
      size,
    });
  };

  const onMouseDown = (e: React.MouseEvent) => {
    setDrag({ startX: e.clientX, startY: e.clientY, cx: crop.x, cy: crop.y });
  };
  useEffect(() => {
    if (!drag) return;
    const onMove = (e: MouseEvent) => {
      const dx = (e.clientX - drag.startX) * (imgSize.w / 480);
      const dy = (e.clientY - drag.startY) * (imgSize.h / (imgSize.h * 480 / imgSize.w));
      setCrop((c) => ({
        ...c,
        x: Math.max(0, Math.min(imgSize.w - c.size, drag.cx + dx)),
        y: Math.max(0, Math.min(imgSize.h - c.size, drag.cy + dy)),
      }));
    };
    const onUp = () => setDrag(null);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, imgSize]);

  const adjustSize = (delta: number) => {
    setCrop((c) => {
      const newSize = Math.max(20, Math.min(Math.min(imgSize.w, imgSize.h), c.size + delta));
      const x = Math.min(imgSize.w - newSize, Math.max(0, c.x));
      const y = Math.min(imgSize.h - newSize, Math.max(0, c.y));
      return { x, y, size: newSize };
    });
  };

  const handleConfirm = async () => {
    if (!imgRef.current) return;
    const canvas = canvasRef.current ?? document.createElement("canvas");
    canvas.width = crop.size;
    canvas.height = crop.size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(imgRef.current, crop.x, crop.y, crop.size, crop.size, 0, 0, crop.size, crop.size);
    canvas.toBlob((blob) => {
      if (blob) onConfirm(blob);
    }, "image/png", 0.92);
  };

  // 表示倍率 (480px max width)
  const scale = imgSize.w ? Math.min(480 / imgSize.w, 480 / imgSize.h) : 1;
  const dispW = imgSize.w * scale;
  const dispH = imgSize.h * scale;

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bf-bg-elev)",
          borderRadius: 12,
          padding: 24,
          maxWidth: 560,
          width: "100%",
          boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--bf-text-1)", marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <CropIcon className="w-4 h-4" />画像をクロップ ({mode === "square" ? "正方形" : "自由"})
        </div>

        <div
          style={{
            position: "relative",
            width: dispW || "100%",
            height: dispH || 320,
            background: "#000",
            margin: "0 auto",
            overflow: "hidden",
            borderRadius: 8,
            cursor: drag ? "grabbing" : "grab",
            userSelect: "none",
          }}
          onMouseDown={onMouseDown}
        >
          {imgUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              ref={imgRef}
              src={imgUrl}
              onLoad={onImgLoad}
              alt="cropping"
              draggable={false}
              style={{ width: "100%", height: "100%", display: "block", pointerEvents: "none" }}
            />
          )}
          {imgSize.w > 0 && (
            <>
              {/* dark overlay outside crop */}
              <div style={{ position: "absolute", inset: 0, boxShadow: `0 0 0 9999px rgba(0,0,0,0.45) inset`, pointerEvents: "none" }} />
              {/* crop box */}
              <div
                style={{
                  position: "absolute",
                  left: crop.x * scale,
                  top: crop.y * scale,
                  width: crop.size * scale,
                  height: crop.size * scale,
                  border: "2px solid var(--bf-primary)",
                  boxShadow: "0 0 0 9999px rgba(0,0,0,0) inset",
                  borderRadius: 4,
                  pointerEvents: "none",
                }}
              />
            </>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 14 }}>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={() => adjustSize(-Math.min(imgSize.w, imgSize.h) * 0.1)}
              style={{ padding: "6px 12px", fontSize: 11, fontWeight: 600, background: "var(--bf-bg)", border: "1px solid var(--bf-border)", borderRadius: 6, cursor: "pointer" }}
            >− 縮小</button>
            <button
              onClick={() => adjustSize(Math.min(imgSize.w, imgSize.h) * 0.1)}
              style={{ padding: "6px 12px", fontSize: 11, fontWeight: 600, background: "var(--bf-bg)", border: "1px solid var(--bf-border)", borderRadius: 6, cursor: "pointer" }}
            >+ 拡大</button>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={onCancel}
              style={{ padding: "8px 14px", fontSize: 12, fontWeight: 600, background: "transparent", border: "1px solid var(--bf-border)", borderRadius: 6, cursor: "pointer", color: "var(--bf-text-2)" }}
            >キャンセル</button>
            <button
              onClick={handleConfirm}
              style={{ padding: "8px 14px", fontSize: 12, fontWeight: 700, background: "var(--bf-primary)", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}
            >この範囲でアップロード</button>
          </div>
        </div>
        <canvas ref={canvasRef} style={{ display: "none" }} />
      </div>
    </div>
  );
}
