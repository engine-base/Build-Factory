# Build-Factory Phase 9 (実装) 完走レビューレポート

> **作成日**: 2026-05-14
> **対象**: 全 187 task の実装完了状態
> **目的**: 仕様徹底度の honest な評価と Phase 10 (レビュー/納品) への引き継ぎ

---

## エグゼクティブサマリー

✅ **数値上は完璧**: 全 187 task の done フラグ確立 / 全 lint pass / 8000 test pass / 全 8 Slice 100%
⚠️ **深さに段階あり**: 30 件は厳密な手動 pre-flight audit、116 件は auto-generated retroactive audit
🔴 **genuine gap 1 件**: T-BTSTRAP-04 (build-factory project migrate) は実装も test も不在

**結論**: **Phase 1 dogfood 着手には十分な完成度。だが「全 187 が同じ深さで verify されている」という主張は誤り**。

---

## 数値レビュー (5 軸)

### 軸 1: tickets.json AC 構造の整合性
- **Total**: 187 / **Compliant**: 187 / **Issues**: 0
- `python3 scripts/validate-tickets.py` で全タスクが必須メタ完備 (`spec_link`, `acceptance_criteria` >=3, EARS canonical type 等)

### 軸 2: EARS AC JSON Schema 検査
- **Total**: 187 tickets / 800 AC / **Issues**: 0
- 5 EARS form (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED) のいずれかに正規化

### 軸 3: lint-mock (構造的禁則)
- **16/16 OK**: 絵文字なし / AGPL なし / ARCHIVE 残留なし / LangGraph 混入なし (ADR-010) / hardcoded secret なし / domain boundary OK / 各種 self-impl 禁則 OK

### 軸 4: 全 backend pytest
- **8000 passed / 10 skipped / 0 failed** (60 秒)
- 1 件 `--deselect` (numpy 互換問題, T-S0-02 範囲外で別 task 追跡)

### 軸 5: verify-slice (Slice/Wave 単位)
- **187/187 PASS / 0 FAIL / 41 warnings** (warnings は audit MD なし系)
- 全 8 Slice 100%

---

## 質的レビュー (深さの段階分析)

### 段階 A: 完璧 (pre-flight audit / 30 件)

手動執筆の audit MD があり、AC × test × impl × lint が個別に厳密検証されている:

```
T-001-04 T-001-05 T-001-06 T-003-02 T-007-01 T-007-03 T-008-01 T-009-01
T-010a-01 T-010a-02 T-010b-01 T-011-01 T-012-01 T-012-02 T-013-04 T-019-01
T-020-02 T-024-02 T-024-03 T-026-01 T-026-03 T-AI-08 T-AI-MEM-01..03
T-IT-S0 T-IT-S3 T-M30-03 T-S0-08 T-BTSTRAP-06
```

**特徴**:
- AC 逐語コピー
- 各 AC sub-clause を impl 行番号で示す表
- regression / cross-module invariant test を含む
- gap closure PR が必要だった場合の経緯も記録

### 段階 B: post-hoc verified (auto-generated retroactive audit / 116 件)

`scripts/generate-audit-mds.py` が自動生成した audit MD。
test ファイル名 pattern matching で AC→test mapping を post-hoc 推定したもの:

```
T-001-01b T-001-02 T-001-03 T-001-07 T-001-08 T-001-10 T-002-02 T-003-01
T-003-05 T-004-05 T-005-02 ... (計 116 件)
```

**信頼度**:
- ✅ test が PASS する (= 機能的に動く)
- ✅ AC は EARS schema に compliant
- ✅ implementation file は existing_files で実在確認済み
- ⚠️ AC sub-clause × impl 行のような **逐語マッピングは未確認**
- ⚠️ regression / invariant test の網羅度は test ファイル次第

### 段階 C: indirect coverage (7 件)

direct な `test_<id>*.py` ファイルが無く、親 task / sibling / 別命名規則の test がカバーしているもの:

| Task | 状況 | 実質カバー |
|---|---|---|
| T-008-04 (phase delete dialog) | 同 page.tsx 内 (T-008-02 と同一ファイル) | T-008-02 test がカバー |
| T-007-03b (DAG semantic fix) | 'b' suffix 修正版 | T-007-03 v2 test がカバー |
| T-024-02b (search silent fix) | 'b' suffix 修正版 | T-024-02 spec test がカバー |
| T-013-04b (Phase 1.5 LLM merge) | Phase 1.5 切り出し | T-013-04 test がカバー |
| T-BTSTRAP-02 (workspace.bootstrap) | service が e2e で動く | T-BTSTRAP-06 e2e test がカバー |
| T-BTSTRAP-06 (e2e workspace) | 別 dir 命名 | tests/e2e/test_workspace_bootstrap.py (6 PASS) |

### 段階 D: **genuine gap (1 件)** 🔴

| Task | 状況 |
|---|---|
| **T-BTSTRAP-04 (build-factory project migrate)** | **実装ファイル無し / test 無し / audit MD は auto-generated だが test 検出失敗中**<br>「既存案件への遡及適用」機能。**Phase 10 で実装すべき** |

---

## Critical Path 12 件の deep check

| # | Task | AC | test | audit MD | 状態 |
|---|---|---:|---:|---|---|
| 1 | T-019-01 | 4 | 41 | ✅ | 完璧 |
| 2 | T-S0-13 | 5 | 92 | ❌ (法外な test 数あるが audit MD 無し) | post-hoc OK |
| 3 | T-001-01 | 5 | 39 | ❌ | post-hoc OK |
| 4 | T-001-02 | 5 | 22 | ✅ | 完璧 |
| 5 | T-001-04 | 5 | 75 | ✅ | 完璧 |
| 6 | T-001-06 | 5 | 50 | ✅ | 完璧 |
| 7 | T-S0-08 | 7 | 66 | ✅ | 完璧 |
| 8 | T-S0-09 | 5 | 66 | ❌ | post-hoc OK |
| 9 | T-021-03 | 5 | 25 | ✅ | 完璧 |
| 10 | T-020-02 | 6 | 74 | ✅ | 完璧 |
| 11 | T-003-02 | 7 | 69 | ✅ | 完璧 |
| 12 | T-M28-01 | 4 | 41 | ❌ | post-hoc OK |

→ **8/12 pre-flight audit / 4/12 post-hoc (test は豊富, audit MD のみ無し)**

---

## AC 内容の深さ分析

| | 件数 | 比率 |
|---|---:|---:|
| 具体的 AC (task-specific spec) | 131 | **70.1%** |
| generic template AC (`The system shall implement T-XXX as specified by feature F-XXX`) | 56 | 29.9% |

**意味**:
- 70% は実装内容に深く根ざした AC (どの DDL / RLS / endpoint / 動作を満たすべきか具体的)
- 30% は EARS スキーマに compliant ではあるが、内容が generic で実装ガイダンスとして弱い

これは **タスク分解 v1 (2026-05-09) 時点での AC 品質ばらつき**。仕様 (M-1〜M-30) の方は具体的なので、AC の generic 版が示唆するのは「該当 task は feature 内の細部実装で、独立した AC が立てづらかった」もの。

---

## Phase 10 (レビュー / 納品) で対処すべき事項

### 🔴 必須対応 (1 件)

1. **T-BTSTRAP-04 (build-factory project migrate)** の実装
   - `templates/CHANGELOG.md` 更新時の既存 workspace 遡及適用
   - PR #290 で T-BTSTRAP-05 (workflow / PR 自動作成) は実装したので、その下回りとなる migrate service が必要

### 🟡 推奨対応 (品質向上)

2. **段階 B の audit MD を pre-flight format に retrofit** (116 件)
   - 特に Critical Path 4 件 (T-S0-13, T-001-01, T-S0-09, T-M28-01) は手動 audit MD を書くべき
   - 残り 112 件は Phase 2 (公開) 前にやれば良い

3. **generic AC 56 件の specific 化**
   - 該当タスクの spec_link (`requirements-v1.html#m-X`) を読み直し、AC を具体化
   - 実装に手は入れなくて済むが、将来の regression 検知が strengthen される

### 🟢 任意 (将来)

4. **Frontend Playwright e2e の追加**
   - 現在 UI は Python static-validation で structure check のみ
   - 実 UX 通しの test は Playwright で別途必要 (T-IT-S7 の Phase 1 dogfood 受入確認の自動化)

5. **DB 実接続 integration test**
   - 現在は SQL ファイル静的解析中心
   - Phase 1 dogfood セットアップ後、実 Supabase 上で migrate → seed → query の通し test

---

## Phase 1 dogfood 受入準備状況

CLAUDE.md §1 "1 人で 10 案件並列運用" の受入には以下が揃っている:

| 機能 | 状態 |
|---|---|
| 認証 + Workspace (S1) | ✅ 完成 |
| AI 社員 + Chat + Memory (S2) | ✅ 完成 |
| ヒアリング → 要件 (S3) | ✅ 完成 |
| アーキ → 機能分解 → タスク分解 (S4) | ✅ 完成 |
| Kanban + DAG + Phase + Cmd+K (S5) | ✅ 完成 |
| MCP + Reviewer + Constitution (S6) | ✅ 完成 |
| Swarm 並列実行 + Worktree (S7) | ✅ 完成 |
| GitHub/Slack/Obsidian/監査 (S8) | ✅ 完成 (T-BTSTRAP-04 を除く) |

**結論**: T-BTSTRAP-04 は Phase 1 dogfood の必須機能ではない (= 既存案件への migrate は 1 件目の dogfood では不要)。**dogfood 着手は今すぐ可能**。

---

## 最終評価

| 軸 | 評価 | コメント |
|---|---|---|
| **数値完成度** | ⭐⭐⭐⭐⭐ | 187/187 全て done フラグ、8000 test pass、lint 16/16 |
| **仕様徹底度 (Pre-flight)** | ⭐⭐⭐ | 30/187 が厳密、116/187 が post-hoc |
| **実装の動作確認** | ⭐⭐⭐⭐ | unit test + static analysis OK、実 DB 通し未確認 |
| **regression 防御** | ⭐⭐⭐⭐ | lint 16/16 + 8000 test + Slice invariant |
| **dogfood 着手可能性** | ⭐⭐⭐⭐⭐ | T-BTSTRAP-04 を除き全 feature 揃っている |

**総合**: ⭐⭐⭐⭐ (Phase 1 着手に十分、Phase 2 公開前に retrofit 推奨)

---

## 次のアクション (推奨優先度順)

1. **🌟 Phase 1 dogfood セットアップ** (Supabase + Vercel + Oracle Cloud Free)
2. **T-BTSTRAP-04 を実装** (1-2 時間, 既存 T-BTSTRAP-05 workflow の下回り)
3. **Critical Path 4 件の手動 audit MD retrofit** (T-S0-13 / T-001-01 / T-S0-09 / T-M28-01)
4. **CLAUDE.md / HANDOVER.md の Phase 9 完走宣言更新**
5. **Phase 2 (公開) 計画書の準備**
