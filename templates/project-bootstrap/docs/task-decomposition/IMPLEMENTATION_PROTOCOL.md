# 実装プロトコル (SOP) — タスクごとに必ず守る手順

> **新セッションが「T-XXX を実装して」と言われた時、必ずこの 7 ステップを順に踏むこと。**
> ステップを飛ばすと、デザイン違反・仕様未充足・既存実装の二重開発・テスト漏れが発生する。

---

## 0. ファイル位置

このファイル: `docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md`
タスク定義: `docs/task-decomposition/2026-05-09_v1/tickets.json` (159 件)
クリティカルパス: tickets.json の `critical_path` 配列 (12 件)

---

## 1. 7 ステップ (順守必須)

### Step 1. タスクを開く
```bash
# tickets.json から T-XXX を探す
python3 -c "import json; d=json.load(open('docs/task-decomposition/2026-05-09_v1/tickets.json')); t=next(x for x in d['tickets'] if x['id']=='T-XXX'); import pprint; pprint.pprint(t)"
```

確認すべき: `id / title / sprint / feature / layer / label / deps / blocks`

### Step 2. メタ完備チェック → 不足なら補完
```bash
python3 scripts/validate-tickets.py
```

このタスクが以下すべてを持っているか:
- [ ] `acceptance_criteria` (EARS 形式 ≥ 3 件、UNWANTED 含む)
- [ ] `spec_link` (要件 M-X への anchor)
- [ ] `mock_link` (UI タスクなら S-XXX のパス)
- [ ] `existing_files` (REUSE/REFACTOR/ARCHIVE なら必須)
- [ ] `entities` (DB 関連なら必須)

**不足があれば、まず mary (BA) として補完してから実装に入る。** 仕様を曖昧なまま走らないこと。

### Step 3. 関連成果物を必ず開く
```bash
# 関連モック (UI タスクのみ)
open docs/mocks/2026-05-09_v1/{category}/S-XXX-name.html

# 関連仕様
open docs/requirements/2026-05-09_v1/requirements-v1.html#m-X

# ER 図 (DB タスク)
open docs/architecture/2026-05-09_v1/er-diagram-v1.html

# 既存ファイル (REUSE/REFACTOR)
cat <existing_files の各ファイル>
```

**飛ばし禁止**。実装途中で「モックと違う」「仕様にない」と気づくのは時間の無駄。

### Step 4. 実装方針を 1 行で宣言
```
- ラベル REUSE  → 「変更なし、テスト追加のみ」と明示
- ラベル REFACTOR → 「既存 X を AC-1〜5 を満たすよう修正」と明示
- ラベル NEW    → 「新規ファイル X / Y を作成」と明示
- ラベル ARCHIVE → 「ファイル X を削除、参照を全て除去」と明示
```

### Step 5. 実装
- **CLAUDE.md §5 (絶対ルール) を必ず守る**
- アイコンは Lucide のみ (`<i data-lucide="...">`)
- 主色は `eb-500` (`#1a6648`)
- shadcn/ui を最優先
- 既存ファイルがあれば編集、新規作成は最小化

### Step 6. テスト + lint
```bash
# 1. EARS AC 全件に対してテストを書く
# 各 AC につき最低 1 件のテストケースが紐づく

# 2. テスト実行
cd backend && pytest                      # backend なら pytest
cd frontend && pnpm test                  # frontend なら playwright/vitest

# 3. lint で違反を検出
bash scripts/lint-mock.sh                 # 絵文字 / 非 Lucide / AGPL チェック
ruff check backend/                       # Python
pnpm lint                                  # TypeScript
```

カバレッジ ≥ 70% (Phase 1 ゲート) を確認。

### Step 7. v2.1 適合チェック (REFACTOR タスクは必須)
9 項目チェック:
1. [ ] 仕様書の AC を全て満たすか (EARS 形式で)
2. [ ] テストカバレッジ ≥ 70%
3. [ ] shadcn/ui 使用 (独自 UI なら理由明記)
4. [ ] Lucide Icons のみ (絵文字なし)
5. [ ] ENGINE BASE green (`#1a6648`) を主色
6. [ ] RLS 設定済み (DB タスク)
7. [ ] audit_log 記録あり
8. [ ] エラーハンドリング (ユーザーフレンドリーメッセージ)
9. [ ] AGPL 依存追加なし (`pnpm licenses ls` / `pip-licenses`)

すべて ✅ なら PR 作成。1 つでも ❌ なら修正してから次へ。

---

## 2. PR 作成時のテンプレ

```markdown
## タスク
- ID: T-XXX
- ラベル: REUSE / REFACTOR / NEW / ARCHIVE
- ストーリーポイント: Xpt
- 関連: F-XXX / S-XXX / M-X

## 変更内容
- (1 行で何をしたか)

## EARS AC 充足確認
- [x] AC-01 (UBIQUITOUS): ...
- [x] AC-02 (EVENT): ...
- [x] AC-03 (STATE): ...
- [x] AC-04 (UNWANTED): ...

## v2.1 適合チェック (REFACTOR の場合)
- [x] 仕様の AC 全充足
- [x] カバレッジ XX%
- [x] shadcn/ui 使用
- [x] Lucide のみ
- [x] eb-500 主色
- [x] RLS / audit_log / エラーハンドリング
- [x] AGPL なし

## テスト
- (実行コマンド + 結果)
```

---

## 3. 並列実行 (Swarm) の場合

T-S0-08 + T-021-03 が完成したら Swarm 起動可能:

```bash
# 例: 4 並列で 4 タスク同時実行
build-factory swarm start --size=4 --tasks="T-001-04,T-001-06,T-S0-09,T-021-03"
```

各セッションが別 git worktree + 別ブランチで作業 → ファイル衝突なし。
crash 時は S-032 セッション詳細 UI で 4 択 resume:
1. **from_checkpoint** = 直前のチェックポイントから再開
2. **rerun_full** = タスク最初からやり直し
3. **manual_fix** = ユーザーが手動修正してから resume
4. **cancel** = タスクをキャンセル、別 AI に振る

---

## 4. やってはいけないこと (絶対 NG)

- ❌ モック / 仕様書を見ずに「だいたいこんな感じ」で実装
- ❌ EARS AC を確認せずに「動いたから OK」と PR
- ❌ 絵文字 (🔍 等) を新規コードに入れる
- ❌ AGPL ライセンスのパッケージを `pnpm add` / `pip install`
- ❌ `--no-verify` / `--force push` (公開後)
- ❌ 本番 DB に対して `DROP / TRUNCATE / DELETE *`
- ❌ `.env` / `credentials.json` を git add
- ❌ 仕様未確定のまま勝手に decisions/ADR-XXX を書き換える

---

## 5. 困った時のエスカレーション

| 状況 | 動き |
|---|---|
| 仕様が曖昧 | mary (BA) として AC を提案 → masato 確認 |
| 既存実装と仕様が矛盾 | 仕様を正とし、REFACTOR で修正。判断保留時は masato 確認 |
| ライブラリ選定で迷う | ADR-002 (AI スタック) / ADR-004 (Hosting) を参照、無ければ新規 ADR |
| Phase 2 機能を Phase 1 で作りたい誘惑 | 却下。`docs/feature-decomposition/` の Phase 区分を守る |
| クリティカルパス外のタスクを先にやりたい | 依存 (`deps`) を確認、blockers が解けてからやる |

---

## 6. このプロトコルの更新

このプロトコル自体を変更する場合:
1. `decisions/ADR-XXX-implementation-protocol-v2.md` で議論
2. masato 承認後、このファイルを更新
3. CLAUDE.md §5 の参照を更新

---

**最終更新: 2026-05-10**
**参照: CLAUDE.md / docs/HANDOVER.md / docs/decisions/**
