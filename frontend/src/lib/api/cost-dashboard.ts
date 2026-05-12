/**
 * T-017-03: cost dashboard API client.
 *
 * Backend contract:
 *   GET /api/observability/cost-summary?dimension=DIM&from=ISO&to=ISO
 *
 * 8 dimensions (T-017-03 backend `VALID_DIMENSIONS` と完全一致 / cross-module):
 *   overview / provider / model / workspace / persona / skill /
 *   period_daily / session
 */

export const VALID_COST_DIMENSIONS = [
  "overview",
  "provider",
  "model",
  "workspace",
  "persona",
  "skill",
  "period_daily",
  "session",
] as const;

export type CostDimension = (typeof VALID_COST_DIMENSIONS)[number];

export interface CostSummaryItem {
  label: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  share: number;
}

export interface CostSummary {
  dimension: string;
  from_iso: string | null;
  to_iso: string | null;
  total_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  items: CostSummaryItem[];
}

export class CostDashboardError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "CostDashboardError";
    this.code = code;
    this.status = status;
  }
}

export interface FetchCostSummaryOptions {
  from?: string;
  to?: string;
  apiBase?: string;
  signal?: AbortSignal;
}

export async function fetchCostSummary(
  dimension: CostDimension,
  opts: FetchCostSummaryOptions = {},
): Promise<CostSummary> {
  if (!VALID_COST_DIMENSIONS.includes(dimension)) {
    throw new CostDashboardError(
      "cost_dashboard.invalid_dimension",
      `dimension must be one of ${VALID_COST_DIMENSIONS.join(",")}`,
      400,
    );
  }
  const base =
    opts.apiBase ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8001";
  const params = new URLSearchParams();
  params.set("dimension", dimension);
  if (opts.from) params.set("from", opts.from);
  if (opts.to) params.set("to", opts.to);
  const resp = await fetch(
    `${base}/api/observability/cost-summary?${params.toString()}`,
    { method: "GET", signal: opts.signal },
  );
  if (!resp.ok) {
    let code = "cost_dashboard.unknown";
    let message = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as {
        detail?: { code?: string; message?: string };
      };
      if (data?.detail?.code) code = data.detail.code;
      if (data?.detail?.message) message = data.detail.message;
    } catch {
      // ignore
    }
    throw new CostDashboardError(code, message, resp.status);
  }
  return (await resp.json()) as CostSummary;
}
