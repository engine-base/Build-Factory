-- Penpot 連携: BF プロジェクト/画面 ↔ Penpot Project/File/Frame
-- ─────────────────────────────────────────────
-- design_mocks: 1 BF 画面 = 1 Penpot File (1 frame でも複数 frame でも可)
-- ─────────────────────────────────────────────

-- 旧 design_frames は Onlook 時代のもの。Penpot 移行で不要 (互換のため残置のみ)
-- 新規は design_mocks に集約。

CREATE TABLE IF NOT EXISTS design_mocks (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    feature_id          BIGINT,                  -- 任意: 機能と紐付け
    page_id             BIGINT,                  -- 任意: ページと紐付け
    name                TEXT NOT NULL,           -- 例: "ログイン画面"
    description         TEXT,
    route_path          TEXT,                    -- 例: "/login"
    -- Penpot 側 ID
    penpot_team_id      TEXT,
    penpot_project_id   TEXT,
    penpot_file_id      TEXT,
    penpot_page_id      TEXT,
    penpot_frame_id     TEXT,                    -- 任意: 単一フレームを指定する場合
    -- BF 側成果物
    preview_image_url   TEXT,                    -- サムネイル
    svg_url             TEXT,                    -- SVG エクスポート
    spec_markdown       TEXT,                    -- Markdown 仕様書 (Phase 5)
    spec_meta           JSONB DEFAULT '{}'::jsonb,
    -- ステータス
    status              TEXT NOT NULL DEFAULT 'draft',
                        -- draft / in_progress / review / approved / archived
    created_by_user_id  TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_design_mocks_workspace ON design_mocks(workspace_id);
CREATE INDEX IF NOT EXISTS ix_design_mocks_status ON design_mocks(status);
CREATE INDEX IF NOT EXISTS ix_design_mocks_penpot_file ON design_mocks(penpot_file_id);

DROP TRIGGER IF EXISTS trg_design_mocks_touch ON design_mocks;
CREATE TRIGGER trg_design_mocks_touch
    BEFORE UPDATE ON design_mocks
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- workspaces に Penpot Project ID を保持 (BF プロジェクト ↔ Penpot プロジェクト 1:1)
ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS penpot_team_id TEXT,
    ADD COLUMN IF NOT EXISTS penpot_project_id TEXT;

COMMENT ON TABLE design_mocks IS 'BF 画面と Penpot File/Frame の紐付け + 成果物';
COMMENT ON COLUMN design_mocks.penpot_file_id IS 'Penpot File UUID。/design-editor/{file_id} で iframe 表示';
COMMENT ON COLUMN design_mocks.status IS 'draft / in_progress / review / approved / archived';
