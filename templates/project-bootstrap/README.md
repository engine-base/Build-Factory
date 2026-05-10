# project-bootstrap テンプレート

Build-Factory が **新案件 (workspace) を作成するときに自動展開する** スケルトン。

## 何が含まれているか

| ファイル | 役割 | プレースホルダ |
|---|---|---|
| `CLAUDE.md.j2` | 新セッション自動読み込み引き継ぎ書 | `{{project_name}}`, `{{client_name}}`, `{{deadline}}`, `{{tech_stack}}`, `{{ai_employees}}` |
| `docs/HANDOVER.md.j2` | 全成果物の統合インデックス | 同上 |
| `docs/decisions/README.md` | ADR の運用ルール | なし |
| `docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md` | タスク実装の 7 ステップ SOP (Build-Factory 共通) | なし |
| `scripts/lint-mock.sh` | 絵文字 / AGPL / メタ検証 | なし |
| `scripts/validate-tickets.py` | tickets.json EARS AC 検証 | なし |
| `.claude/settings.json` | Hook (PostToolUse) + permissions deny | なし |
| `.gitignore` | 一般的な ignore + Build-Factory 固有の除外 | なし |

## 自動展開の流れ (T-BTSTRAP-02 で実装)

```
案件作成 UI  →  POST /api/workspaces  →  WorkspaceService.bootstrap()
   1. workspaces レコード作成
   2. GitHub repo 作成
   3. このテンプレを clone → Jinja2 で {{プレースホルダ}} 置換
   4. 初回 commit + push
   5. Phase 1 (ヒアリング) を開始可能に
```

## プレースホルダ一覧

| 名前 | 例 |
|---|---|
| `{{project_name}}` | 受託EC構築 #4 |
| `{{project_slug}}` | proj-ec-4 |
| `{{client_name}}` | 株式会社 XX |
| `{{deadline}}` | 2026-08-15 |
| `{{phase}}` | 1 (Phase 1) |
| `{{owner_email}}` | masato@engine-base.com |
| `{{tech_stack}}` | Next.js 15 / FastAPI / Supabase |
| `{{ai_employees}}` | mary, winston, devon, quinn, sally |
| `{{template_version}}` | 1.0.0 |
| `{{generated_at}}` | 2026-05-10 |

## テンプレ自体の更新ルール

1. このテンプレを変更したら **`templates/CHANGELOG.md`** に必ず追記
2. masato 承認後、CI が全案件に対し `migrate dry-run` 実行 → 影響範囲を表示
3. 承認されたら全案件に PR 自動作成 (各案件の owner がレビュー)

## 検証

```bash
# テンプレ自体の整合性
bash templates/project-bootstrap/scripts/lint-mock.sh

# プレースホルダ未置換が無いか (実装後)
build-factory templates check
```

## 関連

- ADR-009: project-bootstrap-enforcement
- 機能: F-003 workspace_management
- 実装タスク: T-BTSTRAP-01 〜 T-BTSTRAP-06
