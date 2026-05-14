// T-016-01: obsidian_vaults 設定 UI (REFACTOR: existing obsidian_sync 活用)
//
// AC マッピング:
//   AC-1 UBIQUITOUS: feature F-016 として obsidian vault 一覧 + 設定
//   AC-2 EVENT-DRIVEN: vault 追加/編集/削除で /api/obsidian/vaults に CRUD
//   AC-3 STATE-DRIVEN: backwards-compat with existing obsidian_sync.py
//   AC-4 UNWANTED: invalid vault path / unauthorized → 4xx 表示

"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, Trash2, AlertTriangle, RefreshCcw } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type Vault = {
  id: number;
  name: string;
  path: string;
  sync_enabled: boolean;
  last_synced_at?: string;
};

export default function ObsidianVaultsPage() {
  const qc = useQueryClient();
  const [newVaultPath, setNewVaultPath] = useState("");
  const [newVaultName, setNewVaultName] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: vaults = [] } = useQuery<Vault[]>({
    queryKey: ["obsidian-vaults"],
    queryFn: () => fetch(`${API}/api/obsidian/vaults`).then(r => r.json()),
  });

  const addMutation = useMutation({
    mutationFn: async ({ name, path }: { name: string; path: string }) => {
      const r = await fetch(`${API}/api/obsidian/vaults`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, path }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `add failed (${r.status})`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["obsidian-vaults"] });
      setNewVaultName("");
      setNewVaultPath("");
      setErrorMessage(null);
    },
    onError: (e: Error) => setErrorMessage(e.message),
  });

  const syncMutation = useMutation({
    mutationFn: async (vaultId: number) => {
      const r = await fetch(`${API}/api/obsidian/vaults/${vaultId}/sync`, { method: "POST" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `sync failed (${r.status})`);
      }
      return r.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["obsidian-vaults"] }),
    onError: (e: Error) => setErrorMessage(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: async (vaultId: number) => {
      const r = await fetch(`${API}/api/obsidian/vaults/${vaultId}`, { method: "DELETE" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `delete failed (${r.status})`);
      }
      return r.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["obsidian-vaults"] }),
    onError: (e: Error) => setErrorMessage(e.message),
  });

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 flex items-center gap-2 text-eb-500">
        <FolderOpen className="w-6 h-6" /> Obsidian Vaults
      </h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-100 border border-red-300 text-red-700 rounded flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {errorMessage}
        </div>
      )}

      <div className="mb-6 p-4 border rounded">
        <h2 className="font-bold mb-2">Add new vault</h2>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Vault name"
            value={newVaultName}
            onChange={e => setNewVaultName(e.target.value)}
            className="flex-1 p-2 border rounded focus:border-eb-500 focus:outline-none"
          />
          <input
            type="text"
            placeholder="/path/to/vault"
            value={newVaultPath}
            onChange={e => setNewVaultPath(e.target.value)}
            className="flex-2 p-2 border rounded focus:border-eb-500 focus:outline-none"
          />
          <button
            onClick={() => addMutation.mutate({ name: newVaultName, path: newVaultPath })}
            disabled={!newVaultName || !newVaultPath || addMutation.isPending}
            className="px-4 py-2 bg-eb-500 text-white rounded hover:bg-eb-700 disabled:opacity-50 flex items-center gap-1"
          >
            <Plus className="w-4 h-4" /> Add
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {vaults.map(v => (
          <div key={v.id} className="p-3 border rounded flex justify-between items-center hover:border-eb-500">
            <div>
              <div className="font-medium">{v.name}</div>
              <div className="text-xs text-gray-500 font-mono">{v.path}</div>
              {v.last_synced_at && <div className="text-xs text-gray-400">last sync: {v.last_synced_at}</div>}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => syncMutation.mutate(v.id)}
                disabled={syncMutation.isPending}
                className="p-2 hover:bg-gray-100 rounded text-eb-500"
                aria-label="Sync vault"
              >
                <RefreshCcw className="w-4 h-4" />
              </button>
              <button
                onClick={() => deleteMutation.mutate(v.id)}
                className="p-2 hover:bg-red-100 rounded text-red-600"
                aria-label="Delete vault"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
