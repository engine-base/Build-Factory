# Build-Factory Obsidian Vault

AI 社員 + 人間メンバー共有のナレッジハブ。

## 階層
- `accounts/{account}/shared/` — 会社共有
- `accounts/{account}/members/{user}/private/` — 個人のみ
- `accounts/{account}/members/{user}/shared-with-team/` — チーム共有
- `accounts/{account}/ai-personas/{persona}/` — AI 専用知識
- `workspaces/{workspace}/shared/` — 案件共有
- `workspaces/{workspace}/ai-personas/{persona}/` — 案件×AI

ファイルを変更すると自動で Supabase Postgres (knowledge_base) と同期されます。
