-- design_frames に HTML 本文 + プロンプト履歴 + design spec エクスポート情報を追加
-- ─────────────────────────────────────────────
-- content        : AI が生成した HTML 本文（iframe srcdoc で表示）
-- design_tokens  : 適用したデザインシステムのトークン (colors, typography 等)
-- prompt_history : ユーザー → AI のやりとり履歴 (JSON 配列)
-- spec_meta      : Claude Code 実装フェーズに渡す追加メタ情報
-- ─────────────────────────────────────────────

ALTER TABLE design_frames
    ADD COLUMN IF NOT EXISTS content TEXT,
    ADD COLUMN IF NOT EXISTS design_tokens JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS prompt_history JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS spec_meta JSONB DEFAULT '{}'::jsonb;

-- frame_type 拡張: 'web'(URL) / 'mockup'(AI生成HTML) / 'image' / 'sketch'
COMMENT ON COLUMN design_frames.frame_type IS
    'web=外部URL, mockup=AI生成HTML(content有り), image=画像URL, sketch=手描き';
COMMENT ON COLUMN design_frames.content IS
    'mockup タイプの場合、iframe srcdoc に流す HTML 本文';
COMMENT ON COLUMN design_frames.spec_meta IS
    'Claude Code 実装フェーズに渡す仕様情報 (target_route, components_to_use 等)';

-- デザイナー AI persona を追加（既存の 7 personas に加えて 8 番目）
INSERT INTO ai_employee_config
    (employee_name, display_name, category, primary_skill, persona_name,
     personality, tone_style, catchphrase, avatar_emoji, specialty, account_id, is_active)
VALUES
    ('designer', 'デザイナー', 'design', 'frontend-design', 'ユイ',
     'クリエイティブで観察眼が鋭い。トレンドより本質を重視する。',
     '優しく丁寧、提案型',
     '見やすさは正義です',
     '🎨', 'HTML/CSS/Tailwindでビジュアル豊かなモック生成・要素編集', 1, TRUE)
ON CONFLICT DO NOTHING;
