# T-003-01: BMAD 12 ペルソナ → 10 メンバー persona prompt 整理

CLAUDE.md §3 で定義された **Build-Factory 用 BMAD 10 ペルソナ** の system prompt
を一元管理する場所。BMAD framework の元 12 ペルソナから Build-Factory 用に
10 へ整理した経緯と prompt format をここに集約。

## 12 → 10 マッピング (BMAD 元 → Build-Factory)

| 元 BMAD (12) | Build-Factory (10) | 備考 |
|---|---|---|
| 1. Analyst | **mary** (BA) | そのまま採用 |
| 2. PM | **preston** (PM) | そのまま採用 |
| 3. Architect | **winston** (Architect) | そのまま採用 |
| 4. PO | **sally** (PO) | そのまま採用 |
| 5. SM (Scrum Master) | (削除) | Phase 1 では 1 人運用なので不要 |
| 6. Dev | **devon** (Developer) | そのまま採用 |
| 7. QA | **quinn** (QA) | そのまま採用 |
| 8. Reviewer | **reviewer** (Code Reviewer) | Quinn と独立した PR レビュー特化 |
| 9. UX-Expert | **brand** + **mockup** | デザイン系を 2 役に分割 (brand=ブランド全体 / mockup=画面実装) |
| 10. BMad-Master | (削除) | secretary が代替 (松本の複製、別ファイル管理) |
| 11. BMad-Orchestrator | (削除) | claude-agent-sdk Subagent (Task tool) が代替 (ADR-010) |
| 12. (拡張) | **logan** (Knowledge Curator) | Build-Factory 独自、ナレッジ整理担当 |

### Build-Factory 用 10 ペルソナ (最終構成)

| # | persona_key | 役割 | 主担当 module |
|---|---|---|---|
| 1 | mary | Business Analyst | M-1 / M-2 (顧客対応) |
| 2 | preston | Project Manager | M-3 / M-4 (スケジュール) |
| 3 | winston | Architect | M-5 / M-6 (技術判断) |
| 4 | sally | Product Owner | 要件オーナー |
| 5 | devon | Developer | 実装 |
| 6 | quinn | QA Engineer | テスト |
| 7 | reviewer | Code Reviewer | PR レビュー |
| 8 | brand | Brand Designer | デザインシステム |
| 9 | mockup | UI Mockup | 画面実装 |
| 10 | logan | Knowledge Curator | ナレッジ整理 |

加えて **secretary** (松本の複製) は `~/.claude/skills/secretary/` で別管理。

## Prompt format (各 *.md の構造)

各 persona の system prompt は以下の Markdown sections で構成:

```markdown
# {persona_name} ({persona_key})

## Role
1 行で役割を要約。

## Personality
性格・行動原理。

## Tone Style
会話の調子・言葉遣い。

## Catchphrase
よく使う口癖 / 思考パターン。

## Specialty
専門領域 (handles する module / feature)。

## Constraints
やってはいけないこと、責任範囲外。

## Handoff
他のペルソナへ引き継ぐべきケース。
```

## ADR-010 整合性 (Subagent / handoff の責務分離)

ADR-010 で確認: **handoff (persona 間引継ぎ) は claude-agent-sdk Subagent
(Task tool)** が自動で行う。本ディレクトリの prompt は各 persona の
**system prompt 内容** のみで、orchestration ロジックは含まない。

T-M27-03 (`backend/services/handoff_service.py`) が Subagent wrapper として
本 prompt 群を使う設計。

## 既存 DB seed との関係

`supabase/migrations/20260512400000_bmad_personas_seed.sql` で
`ai_personas` テーブルに 10 行が INSERT されている。本ディレクトリの md
ファイルは DB の `personality` / `tone_style` / `specialty` カラムの
**source of truth** で、DB は cache 的に使う。

## Loader

`backend/services/bmad_persona_prompts.py` の `load_persona_prompt(persona_key)`
で本ディレクトリから prompt を読み出せる。graceful degradation:
ファイルが存在しない / 読込失敗 → None を返し caller で fallback (DB seed
の `personality` カラム等を使う)。
