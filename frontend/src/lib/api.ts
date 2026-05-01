const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type LLMProvider = "claude" | "openai" | "ollama" | "lmstudio" | "litellm";

// ── Dashboard ────────────────────────────────────────────────────────────────

export async function fetchKpi() {
  const res = await fetch(`${BASE}/api/dashboard/kpi`);
  return res.json();
}

export async function fetchRevenueTrend() {
  const res = await fetch(`${BASE}/api/dashboard/revenue-trend`);
  return res.json();
}

export async function fetchPipelineByStage() {
  const res = await fetch(`${BASE}/api/dashboard/pipeline-by-stage`);
  return res.json();
}

export async function fetchPipeline(limit = 20) {
  const res = await fetch(`${BASE}/api/dashboard/pipeline?limit=${limit}`);
  return res.json();
}

export async function fetchTasks(limit = 30) {
  const res = await fetch(`${BASE}/api/dashboard/tasks?limit=${limit}`);
  return res.json();
}

export async function fetchExpenses() {
  const res = await fetch(`${BASE}/api/dashboard/expenses`);
  return res.json();
}

export async function fetchContacts(limit = 50) {
  const res = await fetch(`${BASE}/api/dashboard/contacts?limit=${limit}`);
  return res.json();
}

// ── Records ──────────────────────────────────────────────────────────────────

export async function fetchFolders(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/records/folders`);
  return res.json();
}

export async function fetchRecords(folder = "") {
  const url = folder ? `${BASE}/api/records?folder=${encodeURIComponent(folder)}` : `${BASE}/api/records`;
  const res = await fetch(url);
  return res.json();
}

export async function fetchRecord(path: string) {
  const res = await fetch(`${BASE}/api/records/file?path=${encodeURIComponent(path)}`);
  return res.json();
}

// ── LLM ──────────────────────────────────────────────────────────────────────

export async function fetchProviders() {
  const res = await fetch(`${BASE}/api/llm/providers`);
  return res.json();
}

export async function fetchOllamaModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/llm/ollama/models`);
  return res.json();
}

// ── Chat (SSE streaming) ──────────────────────────────────────────────────────

export async function* streamChat(message: string, provider: LLMProvider, model?: string) {
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, provider, model }),
  });

  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") return;
      try {
        const parsed = JSON.parse(data);
        if (parsed.chunk) yield parsed.chunk as string;
        if (parsed.error) throw new Error(parsed.error);
      } catch {
        // ignore parse errors
      }
    }
  }
}
