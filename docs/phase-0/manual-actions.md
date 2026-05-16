# Phase 0 完了後の Manual Actions (要 repo owner / organization owner 実行)

> Phase 0 完成後、Phase 1 の auto-merge ループを稼働させるため、repo / organization 設定の手動変更が必要。
> 本ドキュメントは高本まさと (organization owner) が実行する設定変更を網羅。

## F4: GitHub Actions Workflow Permissions

### 目的
`.github/workflows/auto-merge.yml` が `gh pr merge --auto --squash` を実行するために `GITHUB_TOKEN` で `pull-requests: write` permission が必要。デフォルトでは read-only。

### 設定手順
1. GitHub web で organization `engine-base` → Settings → Actions → General
2. **Workflow permissions** セクション:
   - ☑ Read and write permissions (Read repository contents and packages permissions の代わり)
   - ☑ Allow GitHub Actions to create and approve pull requests
3. **Save**

### 検証
- 設定後、本 follow-up PR が `auto-merge.yml` 経由で merge されることを観察
- もし merge されない場合、`actions` tab で workflow run のログを確認 (`permission denied` 等のエラーが出る)

### 影響範囲
- organization 配下の全 repository に影響
- 既存の private repo / public repo どちらにも影響

---

## F5: Branch Protection Rules

### 目的
`auto-merge.yml` が即時 merge してしまうと、CI が走り終わる前に PR が merge されてしまうリスク。`ci-v3.yml` の `gate-summary` job を **required check** に登録することで、確実に gate 全 pass 後のみ merge される。

### 設定手順
1. GitHub web で repo `engine-base/Build-Factory` → Settings → Branches → Branch protection rules
2. **Add rule** (or edit existing rule for `main`):
   - Branch name pattern: `main`
   - ☑ Require status checks to pass before merging
     - Search for `gate-summary` (from ci-v3.yml) → ☑
     - Search for `gate-foundation` / `gate-backend` / `gate-ui` / `gate-polish` → ☑ (個別 gate も required にする)
   - ☑ Require branches to be up to date before merging
   - ☑ Require linear history (squash merge と相性 OK)
   - ☑ Do not allow bypassing the above settings (admin 含む)
   - ☐ Require pull request reviews (auto-merge を使うなら disable)
3. **Create / Save changes**

### 検証
- 設定後、本 follow-up PR (or 次の任意 PR) で:
  - CI 完走前は merge ボタン無効化される
  - `gate-summary` が green になった瞬間に `auto-merge.yml` が trigger される
  - status check が全 green なら auto-merge 実行
- `failure-counter` job が動作するかも併せて確認 (1 件失敗 → failure-1 label / 3 件失敗 → needs-human-review label)

### 影響範囲
- main branch 直接 push 禁止 (PR 経由必須)
- admin も bypass 不可

---

## F4 + F5 完了確認チェックリスト

- [ ] organization settings → Workflow permissions: Read and write + create/approve PR が ON
- [ ] repo settings → Branches → main: status check で gate-summary + 4 gate が required
- [ ] テスト PR を 1 件作成し以下を観察:
  - [ ] ci-v3.yml が trigger される
  - [ ] 4 gate が順次実行される
  - [ ] gate-summary が green → auto-merge.yml が trigger
  - [ ] auto-merge.yml が `gh pr merge --auto --squash` 実行
  - [ ] PR が main にマージされる
- [ ] テスト PR を 1 件 failure simulate (例: validate-tickets を意図的に fail):
  - [ ] ci-v3.yml の gate-foundation が fail
  - [ ] gate-backend 以降は skip
  - [ ] gate-summary が `passed: false` で artifact upload
  - [ ] auto-merge は実行されない
  - [ ] failure-counter が動作、`failure-1` label 付与
- [ ] 3 連続失敗 PR で `needs-human-review` label が付くこと

---

## Phase 1 開始前の前提条件

F4 + F5 完了後、Phase 1 の v3 並列実行 (30-50 並列 / auto-merge) が稼働可能になる。
F4 + F5 未完了で Phase 1 を開始すると以下のリスク:
- auto-merge が動作しない (token scope 不足) → 全 PR が manual merge になり、30-50 並列の意味が薄れる
- branch protection なし → 不完全な PR が誤って merge されるリスク

---

## 参考

- T-FOUNDATION-07 PR #309 (ci-v3.yml)
- T-FOUNDATION-08 PR #310 (auto-merge.yml)
- skills/schedule-design/references/v3-core.md (auto-merge 仕様)
