# project-bootstrap テンプレート 変更履歴

## v1.1.0 (2026-05-10)

完了判定ゲートの統合 (ADR-011 連動)。

### 追加
- `scripts/pre-commit-check.sh` — 4 段階の完了ゲート (lint / py-syntax / backend-smoke / frontend-tsc)
- `.claude/settings.json` の Bash hook を強化: `git commit` 検出時に `.last-precommit-check` の有無 / 鮮度 / `exit_code` を確認しブロック警告
- `permissions.allow` に `bash scripts/pre-commit-check.sh*` を追加

### 影響
- 新規案件 / migrate 対象案件は `bash scripts/pre-commit-check.sh` を完了報告前に必ず実行する運用に変わる
- 各案件の `.last-precommit-check` および `.tsc-baseline` は **`.gitignore` 推奨** (環境固有のため)

## v1.0.0 (2026-05-10)

初版リリース。

### 含まれるもの
- `CLAUDE.md.j2` — Jinja2 テンプレート (10 プレースホルダ)
- `docs/HANDOVER.md.j2` — 統合インデックス
- `docs/decisions/README.md` — ADR 運用ルール
- `docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md` — 7 ステップ SOP (Build-Factory 共通)
- `scripts/lint-mock.sh` — 絵文字 / AGPL / メタ検証
- `scripts/validate-tickets.py` — tickets.json EARS AC 検証
- `.claude/settings.json` — PostToolUse hook + permissions deny

### Build-Factory 本体との対応
このテンプレは Build-Factory 本体の `f07ee8a` コミット時点の機械的強制レイヤーをスケルトン化したもの。

### 既知の TODO
- [ ] T-BTSTRAP-02: WorkspaceService.bootstrap() で自動展開ロジック実装
- [ ] T-BTSTRAP-03: Jinja2 プレースホルダ置換エンジン
- [ ] T-BTSTRAP-04: 既存案件への migrate コマンド
- [ ] T-BTSTRAP-05: テンプレ更新時の全案件への伝播 (PR 自動作成)

### プレースホルダ仕様
| 名前 | 必須 | デフォルト |
|---|---|---|
| `{{project_name}}` | ✅ | - |
| `{{project_slug}}` | ✅ | (project_name から自動生成) |
| `{{client_name}}` | ✅ | - |
| `{{deadline}}` | - | "未定" |
| `{{phase}}` | - | "1" |
| `{{owner_email}}` | ✅ | "masato@engine-base.com" |
| `{{tech_stack}}` | - | "Next.js 15 / FastAPI / Supabase" |
| `{{ai_employees}}` | - | "mary, winston, devon, quinn, sally" |
| `{{template_version}}` | 自動 | "1.0.0" |
| `{{generated_at}}` | 自動 | (コマンド実行時刻) |

## 更新ルール

このテンプレを変更する場合:
1. このファイル (CHANGELOG.md) に変更内容を追記
2. `templates/project-bootstrap/CLAUDE.md.j2` の `{{template_version}}` を bump
3. masato 承認後、CI が全案件に対し `migrate dry-run` 実行
4. 承認されたら全案件に PR 自動作成
