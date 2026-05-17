# Group C-3 (UI / Vertical Slice — Screen-Missing Backfill) タスク一覧

> Build-Factory v3 **Phase 1.0-fix** Wave 0 task B.
> 直近の「Phase 1 完了」宣言が 55 screen の frontend 実装欠落を見逃していた点を **正式チケット化** して再走するための分解。
> Source-of-truth: [`docs/functional-breakdown/2026-05-16_v3/screen-drift-summary.md`](../../functional-breakdown/2026-05-16_v3/screen-drift-summary.md) — 64 mock 中 frontend なし 55、hint match 9。

---

## サマリ

| 項目 | 値 |
|---|---|
| 担当 category | account / ai / auth / client / dialog / email / export / extras / moat / onboarding / review / spec / system / task / workspace (15) |
| 対象 screen 数 (drift summary 「missing」) | **55** |
| 実 task 数 (1 task = 1 screen Vertical Slice) | **55** |
| ID range | `T-V3-C3-001` 〜 `T-V3-C3-055` |
| Label 構成 | NEW 55 (全件 frontend ページ未生成扱い — drift summary の impl_status=missing に準拠) |
| 合計工数見積 | **155h** / 55 session |
| Wave 構成 | **W1 = 31 task / 87h** (onboarding + auth + dashboard + 主要 system 系) / **W2 = 24 task / 68h** |
| group / phase | C-3 / Phase 1.0-fix |
| deliverable_layer | ui (全件) |
| branch | `claude/T-V3-C3-<NNN>` (各 task 1 branch) |
| Foundation 依存 | Phase 0 完成済 (T-FOUNDATION-01〜08) |
| Group B 依存 | 各 task の `depends_on` に `T-V3-B-<NN>` を cross-ref。leaf = 13 (dialog 5 / system 4 / export 2 / extras 2) |
| 必須 risk_flag | `depends-on-T-V3-C-TEST-01` (vitest infra 共通) — 全 55 task に付与 |

---

## Wave 配分の方針

W1 (Wave 1 / First) は **オンボーディング fatal path** + **ログイン以降の最低限の使い始めフロー** を埋める。具体的には:

- **auth (5)**: S-001〜S-005 — login / signup / password reset / MFA / OAuth callback (全 page 未着手だと全画面が孤立)
- **onboarding (3)**: S-048〜S-050 — welcome / workspace setup / AI 社員紹介
- **system (4)**: S-044〜S-047 — 404 / 500 / 403 / maintenance (guarded route の fall-back に必須)
- **workspace 主軸 (4)**: S-012 dashboard / S-013 settings / S-014 members / S-015 invite
- **account 周辺 (2)**: S-006 account dashboard / S-008 account members
- **email 招待系 (3)**: S-056 signup-verify / S-057 password-reset / S-058 invitation
- **dialog 認証系 (2)**: S-053 MFA challenge / S-054 session expired
- **global utilities (2)**: S-010 通知 inbox / S-011 グローバル検索 (Cmd+K)
- **task daily-driver (2)**: S-027 タスク Kanban / S-030 タスク詳細
- **moat 統制 (2)**: S-018 Constitution エディタ / S-019 赤線設定
- **spec (2)**: S-021 要件エディタ / S-022 仕様書ビューア

W2 (Wave 2) は **client / dialog 残り / export / extras / ai 詳細 / spec 残り (5b) / review / dag / swarm 詳細 / email task-system系** で構成。

---

## category × task

### account (4 task / 12h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-001 | S-006 10 案件 俯瞰 (F-024) | W1 | 3.0h | T-V3-B-27 |
| T-V3-C3-002 | S-008 メンバー管理 (F-004) | W1 | 3.0h | T-V3-B-05, T-V3-B-06 |
| T-V3-C3-003 | S-010 通知 Inbox (F-018) | W1 | 3.0h | T-V3-B-24, T-V3-B-25 |
| T-V3-C3-004 | S-011 グローバル検索 Cmd+K (F-024) | W1 | 3.0h | T-V3-B-27 |

### ai (1 task / 3h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-005 | S-037 AI 社員 詳細 (F-003) | W2 | 3.0h | T-V3-B-04 |

### auth (5 task / 14h) — 全件 W1

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-006 | S-001 ログイン | W1 | 3.0h | T-V3-B-01, T-V3-B-02 |
| T-V3-C3-007 | S-002 サインアップ | W1 | 3.0h | T-V3-B-01, T-V3-B-02 |
| T-V3-C3-008 | S-003 パスワード再設定 | W1 | 3.0h | T-V3-B-01, T-V3-B-02 |
| T-V3-C3-009 | S-004 MFA セットアップ | W1 | 3.0h | T-V3-B-01, T-V3-B-02 |
| T-V3-C3-010 | S-005 OAuth コールバック | W1 | 2.0h | T-V3-B-01, T-V3-B-02 |

### client (2 task / 6h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-011 | S-042 クライアントポータル (F-013) | W2 | 3.0h | T-V3-B-19, T-V3-B-20, T-V3-B-21 |
| T-V3-C3-012 | S-043 クライアントコメント (F-013) | W2 | 3.0h | T-V3-B-19, T-V3-B-20, T-V3-B-21 |

### dialog (5 task / 10h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-013 | S-051 削除確認 | W2 | 2.0h | — (leaf, static) |
| T-V3-C3-014 | S-052 未保存警告 | W2 | 2.0h | — (leaf, static) |
| T-V3-C3-015 | S-053 MFA コード入力 | W1 | 2.0h | — (leaf, integrates with auth) |
| T-V3-C3-016 | S-054 セッション切れ | W1 | 2.0h | — (leaf, integrates with auth) |
| T-V3-C3-017 | S-055 Danger Zone | W2 | 2.0h | — (leaf, static) |

### email (5 task / 10h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-018 | S-056 サインアップ確認メール | W1 | 2.0h | T-V3-B-30 |
| T-V3-C3-019 | S-057 パスワードリセットメール | W1 | 2.0h | T-V3-B-30 |
| T-V3-C3-020 | S-058 招待メール | W1 | 2.0h | T-V3-B-30 |
| T-V3-C3-021 | S-059 タスク通知 | W2 | 2.0h | T-V3-B-30 |
| T-V3-C3-022 | S-060 週次サマリー | W2 | 2.0h | T-V3-B-30 |

### export (2 task / 6h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-023 | S-061 仕様書 PDF | W2 | 3.0h | — (leaf, static template page) |
| T-V3-C3-024 | S-062 納品レポート | W2 | 3.0h | — (leaf, static template page) |

### extras (2 task / 6h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-025 | S-063 検索結果 | W2 | 3.0h | — (leaf — search API は将来追加) |
| T-V3-C3-026 | S-064 API トークン管理 | W2 | 3.0h | — (leaf — token API は将来追加) |

### moat (5 task / 16h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-027 | S-016 フェーズ管理 (F-008) | W2 | 3.0h | T-V3-B-13 |
| T-V3-C3-028 | S-017 依存グラフ (F-009) | W2 | 4.0h | T-V3-B-14 |
| T-V3-C3-029 | S-018 Constitution エディタ (F-026) | W1 | 3.0h | T-V3-B-28 |
| T-V3-C3-030 | S-019 赤線設定 (F-012) | W1 | 3.0h | T-V3-B-17, T-V3-B-18 |
| T-V3-C3-031 | S-034 赤線承認 (F-012) | W2 | 3.0h | T-V3-B-17, T-V3-B-18 |

### onboarding (3 task / 9h) — 全件 W1

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-032 | S-048 ようこそ | W1 | 3.0h | T-V3-B-29 |
| T-V3-C3-033 | S-049 案件セットアップ | W1 | 3.0h | T-V3-B-29 |
| T-V3-C3-034 | S-050 AI 社員紹介 | W1 | 3.0h | T-V3-B-29 |

### review (2 task / 6h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-035 | S-033 PR レビュー (F-013) | W2 | 3.0h | T-V3-B-19, T-V3-B-20, T-V3-B-21 |
| T-V3-C3-036 | S-035 納品承認 (F-013) | W2 | 3.0h | T-V3-B-19, T-V3-B-20, T-V3-B-21 |

### spec (7 task / 23h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-037 | S-020 ヒアリングセッション (F-005) | W2 | 3.0h | T-V3-B-07 |
| T-V3-C3-038 | S-021 要件エディタ (F-006) | W1 | 3.0h | T-V3-B-10 |
| T-V3-C3-039 | S-022 仕様書ビューア (F-005) | W1 | 3.0h | T-V3-B-07 |
| T-V3-C3-040 | S-023 画面モックビューア (F-005b) | W2 | 4.0h | T-V3-B-08, T-V3-B-09 |
| T-V3-C3-041 | S-024 コンポーネントカタログ (F-005b) | W2 | 3.0h | T-V3-B-08, T-V3-B-09 |
| T-V3-C3-042 | S-025 画面遷移マップ (F-005b) | W2 | 3.0h | T-V3-B-08, T-V3-B-09 |
| T-V3-C3-043 | S-026 HTML エディタ (F-005b) | W2 | 4.0h | T-V3-B-08, T-V3-B-09 |

### system (4 task / 8h) — 全件 W1

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-044 | S-044 404 Not Found | W1 | 2.0h | — (leaf, static) |
| T-V3-C3-045 | S-045 500 Server Error | W1 | 2.0h | — (leaf, static) |
| T-V3-C3-046 | S-046 403 Forbidden | W1 | 2.0h | — (leaf, static) |
| T-V3-C3-047 | S-047 Maintenance | W1 | 2.0h | — (leaf, static) |

### task (4 task / 14h)

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-048 | S-027 タスク Kanban (F-007) | W1 | 4.0h | T-V3-B-11, T-V3-B-12 |
| T-V3-C3-049 | S-029 タスク DAG (F-007) | W2 | 4.0h | T-V3-B-11, T-V3-B-12, T-V3-B-14 |
| T-V3-C3-050 | S-030 タスク詳細 (F-006) | W1 | 3.0h | T-V3-B-10, T-V3-B-11, T-V3-B-12 |
| T-V3-C3-051 | S-032 セッション詳細 (F-010c) | W2 | 3.0h | T-V3-B-15, T-V3-B-16 |

### workspace (4 task / 12h) — 全件 W1

| ID | screen | wave | est | depends_on |
|---|---|---|---|---|
| T-V3-C3-052 | S-012 案件ダッシュボード (F-006) | W1 | 3.0h | T-V3-B-11, T-V3-B-12 |
| T-V3-C3-053 | S-013 案件設定 (F-004) | W1 | 3.0h | T-V3-B-05, T-V3-B-06 |
| T-V3-C3-054 | S-014 案件メンバー (F-004) | W1 | 3.0h | T-V3-B-05, T-V3-B-06 |
| T-V3-C3-055 | S-015 メンバー招待 (F-004) | W1 | 3.0h | T-V3-B-05, T-V3-B-06 |

---

## 受け入れ条件 (3-tier EARS) の共通方針

全 55 task は次の構造で `acceptance_criteria` を保持する。詳細は各 task の JSON 参照。

### structural (5 件 / task)

1. `UBIQUITOUS: data-screen-id="S-XXX"` を page root に出す (mock との対応の機械検証フック)
2. `STATE-DRIVEN: h1` を **screens.json の `h1_text` 完全一致** で表示 (空の場合は h1 を出さない明示も含む)
3. `STATE-DRIVEN: section h2` (or KPI labels) を **screens.json の `section_h2_texts` 完全一致** で表示 / セクション無しの screen は 1:1 構造維持を明文化
4. `UBIQUITOUS: Lucide icons 限定` (絵文字禁止 — CLAUDE.md §5.1 / design-tokens.md §8)
5. `UBIQUITOUS: ENGINE BASE green palette (eb-500 = #1a6648)` を primary brand color として固定 (ad-hoc hex 禁止)

### functional (5〜8 件 / task)

- 主要 API endpoint (screens.json `related_apis` の 1st) について `EVENT-DRIVEN: 2xx`, `422`, `5xx` の挙動を網羅
- `UNWANTED: 401` (未認証 → /login) / `UNWANTED: 403` (権限欠落 → /forbidden) (public screen は除く)
- 動的 route (`[id]` を含むもの) に `UNWANTED: 404 → /not-found` を追加
- mutation 系 endpoint がある場合 `UNWANTED: 409` (状態衝突) を追加
- `STATE-DRIVEN: skeleton loader` (role/aria-live) と `empty state` を必須
- features.json の `ears_ac_seed` から 1 件 traceability 用に取り込み (feature ↔ screen の依存可視化)

### regression (3 件 / task)

1. **vitest** : `pnpm vitest run frontend/tests/screens/S-XXX-<slug>.spec.tsx` 緑 + coverage >= 70%
2. **tsc** : `pnpm tsc --noEmit` 0 error (触ったモジュール群)
3. **lint trio**: `bash scripts/lint-mock.sh 17/17 OK` + `bash scripts/audit-md-check.sh T-V3-C3-NNN` 緑 + `bash scripts/lint-mock-impl-diff.sh S-XXX drift_count=0`

---

## work_package_boundary (全 task 共通スケルトン)

```jsonc
{
  "editable": [
    "frontend/src/app/<route_seg>/page.tsx",
    "frontend/src/api/<screen_name>.ts",
    "frontend/src/hooks/use-<screen_name>.ts",
    "frontend/tests/screens/S-XXX-<screen_name>.spec.tsx"
  ],
  "shared_no_concurrent_edit": [
    "frontend/src/app/layout.tsx",
    "frontend/src/api/client.ts",
    "frontend/src/lib/auth.ts"
  ],
  "readonly": [
    "docs/mocks/2026-05-15_v3/<category>/S-XXX-<slug>.html",
    "docs/functional-breakdown/2026-05-16_v3/screens.json",
    "docs/functional-breakdown/2026-05-16_v3/features.json",
    "docs/mocks/2026-05-15_v3/design-system/DESIGN.md"
  ],
  "forbidden": [
    "data/migrations/",
    "backend/"
  ]
}
```

これにより **任意の 1 task は他の 54 task と編集境界が衝突しない** 設計 (各 task が `editable` で claim する path は task ID と 1:1)。

---

## 検証コマンド

```bash
# JSON 妥当性 + v3 3-tier AC schema (must exit 0)
python3 scripts/validate-tickets.py \
  --check-file docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c3-screen-missing.json
# => OK: all tasks pass v3 schema validation. (55/55)

# 既存 lint pipeline (17/17 OK keep)
bash scripts/lint-mock.sh
```

---

## 着手プロトコル

1. **Wave 1 を Foundation 完了直後に並列着手** (auth + onboarding + system + workspace を 31 task 全部走らせる前提で各 task の `work_package_boundary.editable` が完全分離されているのを scheduler で検証)
2. 各 task は **着手前に audit MD (`docs/audit/2026-05-16_v3/T-V3-C3-NNN.md`)** を `_template.md` から起こして埋める (Pre-flight AC audit v2 — `docs/audit/2026-05-13_v2/README.md` の運用に準拠)
3. 完了判定の単一ゲートは `pre-commit-check.sh` (ADR-011)。N/A 禁止 (3 regression AC のうち 1 つでも skip すれば NG)
4. Wave 1 完了 → Wave 2 着手 (W2 24 task / 68h)。Wave 切替時に integration smoke (auth → dashboard → kanban → task detail) を回す
5. 全 55 task done → `lint-mock-impl-diff.sh` で 64 mock 全件 drift_count=0 を確認 → Phase 1.0-fix 完了宣言

---

_Generated by `docs/task-decomposition/2026-05-16_v3_phase1/_generate_group_c3_screen_missing.py` on 2026-05-17._
