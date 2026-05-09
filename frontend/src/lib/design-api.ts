/**
 * Build-Factory design canvas REST client.
 *
 * Onlook 由来の canvas で `api.frame.create.mutate` のような tRPC 呼び出しを
 * していた箇所をこのクライアントに差し替える。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

export interface DesignFrame {
    id: number;
    workspace_id: number;
    branch_id: string | null;
    name: string;
    url: string;
    frame_type: string;
    position_x: number;
    position_y: number;
    width: number;
    height: number;
    z_index: number;
    metadata: Record<string, unknown>;
    has_content?: boolean;
    design_tokens?: Record<string, unknown>;
    spec_meta?: Record<string, unknown>;
    created_at?: string;
    updated_at?: string;
}

export interface MockupGenerateResponse {
    frame: DesignFrame;
    summary: string;
    html: string;
}

export interface CanvasState {
    workspace_id: number;
    user_id: string;
    scale: number;
    position_x: number;
    position_y: number;
    selected_frame_ids: number[];
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const r = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: {
            'Content-Type': 'application/json',
            ...(init.headers || {}),
        },
    });
    if (!r.ok) {
        const text = await r.text().catch(() => '');
        throw new Error(`API ${r.status}: ${text}`);
    }
    if (r.status === 204) return undefined as T;
    return (await r.json()) as T;
}

export const designApi = {
    listFrames: (workspaceId: number, branchId?: string) =>
        req<DesignFrame[]>(
            `/api/workspaces/${workspaceId}/design/frames` +
                (branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''),
        ),
    createFrame: (workspaceId: number, payload: Partial<DesignFrame> & { url: string }) =>
        req<DesignFrame>(`/api/workspaces/${workspaceId}/design/frames`, {
            method: 'POST',
            body: JSON.stringify(payload),
        }),
    updateFrame: (
        workspaceId: number,
        frameId: number,
        payload: Partial<DesignFrame>,
    ) =>
        req<DesignFrame>(
            `/api/workspaces/${workspaceId}/design/frames/${frameId}`,
            {
                method: 'PATCH',
                body: JSON.stringify(payload),
            },
        ),
    deleteFrame: (workspaceId: number, frameId: number) =>
        req<void>(`/api/workspaces/${workspaceId}/design/frames/${frameId}`, {
            method: 'DELETE',
        }),
    getCanvasState: (workspaceId: number, userId?: string) =>
        req<CanvasState>(
            `/api/workspaces/${workspaceId}/design/canvas-state` +
                (userId ? `?user_id=${encodeURIComponent(userId)}` : ''),
        ),
    saveCanvasState: (workspaceId: number, state: CanvasState) =>
        req<CanvasState>(
            `/api/workspaces/${workspaceId}/design/canvas-state`,
            {
                method: 'PUT',
                body: JSON.stringify(state),
            },
        ),
    generateMockup: (
        workspaceId: number,
        body: { prompt: string; name?: string; design_system_ref?: string },
    ) =>
        req<MockupGenerateResponse>(
            `/api/workspaces/${workspaceId}/design/generate-mockup`,
            { method: 'POST', body: JSON.stringify(body) },
        ),
    editMockup: (
        workspaceId: number,
        frameId: number,
        body: { instruction: string; target_selector?: string },
    ) =>
        req<MockupGenerateResponse>(
            `/api/workspaces/${workspaceId}/design/frames/${frameId}/edit`,
            { method: 'POST', body: JSON.stringify(body) },
        ),
};
