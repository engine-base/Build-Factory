-- Design canvas: フレーム + キャンバス状態のテーブル
-- ─────────────────────────────────────────────
-- design_frames    : ワークスペース配下のキャンバスに置かれた個々のフレーム
-- design_canvas_state : ワークスペース×ユーザー単位の zoom/pan 状態
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS design_frames (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    branch_id       TEXT,
    name            TEXT NOT NULL DEFAULT 'Frame',
    url             TEXT NOT NULL,
    frame_type      TEXT NOT NULL DEFAULT 'web',     -- web / image / mockup
    position_x      DOUBLE PRECISION NOT NULL DEFAULT 0,
    position_y      DOUBLE PRECISION NOT NULL DEFAULT 0,
    width           DOUBLE PRECISION NOT NULL DEFAULT 1440,
    height          DOUBLE PRECISION NOT NULL DEFAULT 900,
    z_index         INTEGER NOT NULL DEFAULT 0,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_design_frames_workspace ON design_frames(workspace_id);
CREATE INDEX IF NOT EXISTS ix_design_frames_branch ON design_frames(branch_id);

CREATE TABLE IF NOT EXISTS design_canvas_state (
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL DEFAULT '__workspace_default__',
    scale           DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    position_x      DOUBLE PRECISION NOT NULL DEFAULT 0,
    position_y      DOUBLE PRECISION NOT NULL DEFAULT 0,
    selected_frame_ids JSONB DEFAULT '[]'::jsonb,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_canvas_state_user ON design_canvas_state(user_id);

-- updated_at 自動更新 trigger
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_design_frames_touch ON design_frames;
CREATE TRIGGER trg_design_frames_touch
    BEFORE UPDATE ON design_frames
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_canvas_state_touch ON design_canvas_state;
CREATE TRIGGER trg_canvas_state_touch
    BEFORE UPDATE ON design_canvas_state
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

COMMENT ON TABLE design_frames IS 'Onlook 由来のキャンバスフレーム。workspace 単位で複数配置可能。';
COMMENT ON TABLE design_canvas_state IS 'キャンバスの zoom/pan/selection 状態。user_id 単位で保存。';
