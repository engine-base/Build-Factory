/**
 * Build-Factory ↔ backend designs API client.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

export interface DesignMock {
    id: number;
    workspace_id: number;
    feature_id: number | null;
    page_id: number | null;
    name: string;
    description: string | null;
    route_path: string | null;
    penpot_team_id: string | null;
    penpot_project_id: string | null;
    penpot_file_id: string | null;
    penpot_page_id: string | null;
    penpot_frame_id: string | null;
    preview_image_url: string | null;
    svg_url: string | null;
    spec_markdown: string | null;
    spec_meta: Record<string, unknown>;
    status: string;
    created_at?: string;
    updated_at?: string;
}

export interface EmbedUrlResponse {
    embed_url: string;
    file_id: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
    if (!r.ok) {
        throw new Error(`API ${r.status}: ${(await r.text().catch(() => '')).slice(0, 200)}`);
    }
    if (r.status === 204) return undefined as T;
    return (await r.json()) as T;
}

export const designsApi = {
    list: (workspaceId: number) =>
        req<DesignMock[]>(`/api/workspaces/${workspaceId}/designs`),
    get: (workspaceId: number, designId: number) =>
        req<DesignMock>(`/api/workspaces/${workspaceId}/designs/${designId}`),
    create: (
        workspaceId: number,
        body: { name: string; description?: string; route_path?: string },
    ) =>
        req<DesignMock>(`/api/workspaces/${workspaceId}/designs`, {
            method: 'POST',
            body: JSON.stringify(body),
        }),
    update: (
        workspaceId: number,
        designId: number,
        body: Partial<Pick<DesignMock, 'name' | 'description' | 'route_path' | 'status'>>,
    ) =>
        req<DesignMock>(`/api/workspaces/${workspaceId}/designs/${designId}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
        }),
    delete: (workspaceId: number, designId: number) =>
        req<void>(`/api/workspaces/${workspaceId}/designs/${designId}`, {
            method: 'DELETE',
        }),
    embedUrl: (workspaceId: number, designId: number) =>
        req<EmbedUrlResponse>(
            `/api/workspaces/${workspaceId}/designs/${designId}/embed-url`,
        ),
};
