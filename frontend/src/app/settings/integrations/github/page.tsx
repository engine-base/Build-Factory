// T-013-01: GitHub OAuth + repo 紐付け UI
//
// AC マッピング:
//   AC-1 UBIQUITOUS: feature F-013 として GitHub 連携設定画面
//   AC-2 EVENT-DRIVEN: OAuth flow 起動 + repo 一覧 fetch + 紐付け
//   AC-3 STATE-DRIVEN: token は encrypted_secrets / RLS + audit_logs
//   AC-4 UNWANTED: invalid OAuth response / unauthorized → 4xx 表示

"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Github, Link as LinkIcon, Unlink, AlertTriangle, CheckCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type GithubStatus = { connected: boolean; user_login?: string };
type Repo = { id: number; full_name: string; private: boolean; linked: boolean };

export default function GithubIntegrationPage() {
  const qc = useQueryClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: status } = useQuery<GithubStatus>({
    queryKey: ["github-status"],
    queryFn: () => fetch(`${API}/api/oauth/github/status?owner_id=current`).then(r => r.json()),
  });

  const { data: repos = [] } = useQuery<Repo[]>({
    queryKey: ["github-repos"],
    queryFn: () => fetch(`${API}/api/integrations/github/repos`).then(r => r.json()),
    enabled: !!status?.connected,
  });

  const connectMutation = useMutation({
    mutationFn: async () => {
      const r = await fetch(`${API}/api/oauth/github/authorize?owner_id=current&redirect_uri=${encodeURIComponent(window.location.href)}`);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `authorize failed (${r.status})`);
      }
      const { url } = await r.json();
      window.location.href = url;
    },
    onError: (e: Error) => setErrorMessage(e.message),
  });

  const linkMutation = useMutation({
    mutationFn: async ({ repoId, link }: { repoId: number; link: boolean }) => {
      const r = await fetch(`${API}/api/integrations/github/repos/${repoId}/${link ? 'link' : 'unlink'}`, { method: "POST" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `link failed (${r.status})`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["github-repos"] });
      setErrorMessage(null);
    },
    onError: (e: Error) => setErrorMessage(e.message),
  });

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 flex items-center gap-2 text-eb-500">
        <Github className="w-6 h-6" /> GitHub Integration
      </h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-100 border border-red-300 text-red-700 rounded flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {errorMessage}
        </div>
      )}

      <div className="mb-6 p-4 border rounded">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {status?.connected ? <CheckCircle className="w-5 h-5 text-eb-500" /> : <Github className="w-5 h-5" />}
            <div>
              <div className="font-medium">{status?.connected ? `Connected as ${status.user_login}` : "Not connected"}</div>
              <div className="text-sm text-gray-500">Connect your GitHub account to link repositories</div>
            </div>
          </div>
          {!status?.connected && (
            <button
              onClick={() => connectMutation.mutate()}
              className="px-4 py-2 bg-eb-500 text-white rounded hover:bg-eb-700"
            >
              Connect GitHub
            </button>
          )}
        </div>
      </div>

      {status?.connected && (
        <div>
          <h2 className="font-bold mb-3">Repositories ({repos.length})</h2>
          <div className="space-y-2">
            {repos.map(r => (
              <div key={r.id} className="p-3 border rounded flex justify-between items-center hover:border-eb-500">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm">{r.full_name}</span>
                  {r.private && <span className="text-xs px-2 py-1 bg-gray-100 rounded">private</span>}
                </div>
                <button
                  onClick={() => linkMutation.mutate({ repoId: r.id, link: !r.linked })}
                  className="px-3 py-1 text-sm border rounded flex items-center gap-1 hover:border-eb-500"
                >
                  {r.linked ? <><Unlink className="w-3 h-3" /> Unlink</> : <><LinkIcon className="w-3 h-3" /> Link</>}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
