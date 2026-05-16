---
name: integration
description: 複数ブランチ・複数タスクの実装完了後、本体コードベースへ統合するプロセスを設計するスキル。マージ戦略・コンフリクト対応・統合後の動作確認・ロールバック手順を設計する。v3 採用 (汎用化版): N 並列セッション × N CI gate auto-merge 前提。主軸は (1) Wave 単位の完了集計 (auto-merged / retried / escalated / rolled-back + drift 件数) (2) Phase gate 開放判定 (Foundation → Backend → UI → Polish を mechanical に判定) (3) drift fix queue 流し込み (lint 違反 → drift task 自動生成 → 次 Wave の drift fix group) (4) conflict 原因追跡 (file mutex 漏れ → boundary 修正)。distributed-dev の branch-package.json + wave-schedule.json + gate-config.yml を pull し、file mutex で conflict 事前防止前提。rollback は task 単位 PR revert + drift fix queue Wave 再起動 (reset --hard 禁止)。「ブランチをマージしたい」「統合を進めたい」「コンフリクトが怖い」「統合後の品質確認をしたい」「リリース前の最終チェックをしたい」「並列 Wave 完了を集計したい」「Phase gate 開放判定をしたい」「drift を fix queue に流したい」「wave-integration-report.md を出したい」「phase-gate-decision.json を作りたい」場面で必ず使う。4STEP の対話型プロセス。出力は統合計画書 + 統合管理 JSON + wave-integration-report.md + phase-gate-decision.json の 4 形式。
tab: 品質・運用
builtin: true
---
---

## 全スキル共通：思考品質基準（必ず守ること）

---

### 1. 出力前の必須内部チェック（ユーザーには見せない）

出力を生成する前に、以下を内部で確認する：

- ユーザーの業界・ドメインに固有の法律・規制・制度を参照したか
- 仮説は「売上を上げたい」のような汎用ゴールではなく、そのドメイン・業務フローに固有の仮説になっているか
- 質問は「はい/いいえ」で終わらず、具体例や選択肢を含む設計になっているか
- 曖昧な発言（複数の解釈が可能な表現）に対して複数の解釈を提示したか
- ステークホルダー全員の視点（承認者・反対する人・実際の利用者）を漏らしていないか

---

### 2. 仮説の品質基準

【仮説】ラベルを使う際は以下の形式に従う：

悪い仮説：「売上を増やしたい」「効率化したい」（汎用すぎて意味がない）

良い仮説の構造：
- 現状の問題を業務フロー・技術・組織の観点で具体的に示す
- その問題が発生している原因を特定する
- 解決後にどう状態が変わるかを示す

例（ECサイト文脈）：
「現状のフォーム申し込みでは購入完了までのステップが多く、SIM契約と端末購入を同一フローで完結できないため、途中離脱による機会損失が発生している可能性がある」

---

### 3. 質問設計の基準

質問1つに対して、必要に応じてサブ質問（a, b, c）を設ける。
単一の質問だけでは曖昧さが残る場合は必ずサブ質問に分解する。

例：
① 達成したい状態は何ですか？
  - a. 数値目標があれば教えてください（例：月〇件の受注、工数〇時間削減）
  - b. 現在の方法と比べて「何が変わればOK」ですか？
  - c. 「成功した」と判断する基準は何ですか？

---

### 4. ドメインスキャン（出力前に内部実行）

ユーザーの業界・プロジェクト種別を判定し、以下の対応表から該当する規制・制度を確認する。
該当する規制がある場合、質問の中で必ずそのリスク・注意点に触れること。

| ドメイン | 確認すべき法律・規制・制度 |
|---|---|
| EC・通販・ネットショップ | 特定商取引法（表記義務）、景品表示法、個人情報保護法 |
| SIM・通信・MVNO | 電気通信事業法、本人確認（eKYC）義務、特定商取引法 |
| 医療・ヘルスケア | 薬機法、医療法、個人情報保護法（要配慮個人情報） |
| 金融・保険・投資 | 金融商品取引法、保険業法、マネロン防止法（AML）、本人確認義務 |
| 不動産 | 宅建業法、借地借家法、重要事項説明義務 |
| 飲食・食品・EC | 食品衛生法、景品表示法、アレルギー表示義務 |
| 人材・採用・派遣 | 労働者派遣法、職業安定法、個人情報保護法 |
| 教育・子ども向け | 児童福祉法、個人情報保護法（18歳未満の特別保護） |
| SNS・UGC・プラットフォーム | プロバイダ責任制限法、著作権法、不正競争防止法 |
| 予約・マッチング | 特定商取引法、消費者契約法、個人情報保護法 |
| SaaS・BtoB | 下請法（SIer案件の場合）、NDA・秘密保持義務 |

---

### 5. 曖昧な発言の複数解釈処理

ユーザーの発言に複数の解釈が可能な場合、解釈を並べて確認する。
解釈を単一に絞り込まず、「どちらの意味ですか？」と確認する。

例：「個人情報を特定してほしくない」
→ 解釈A：顧客の個人情報をセキュリティ保護・外部漏洩防止したい
→ 解釈B：サイト上の会社名・運営者情報を表に出したくない（非公開にしたい）
→ 解釈C：特定商取引法上の表記義務との関係（法的に一部表示義務がある項目も存在する）

---

### 6. ステークホルダーの網羅

「誰が使うか」だけでなく以下を常に確認する：
- 誰が承認・決裁するか
- 誰が反対・抵抗する可能性があるか
- 誰がシステムを運用・保守するか
- エンドユーザーと発注者が異なる場合、それぞれのゴールは一致しているか

---

### 7. 質問保留・打ち合わせ優先ルール（全スキル共通）

クライアントから以下のような発言があった場合、即座に質問の送信を停止する：
- 「質問は打ち合わせで」「後で回答します」「今は答えられない」「一旦いただいている内容だけ」
- 「確認できたらまた連絡します」「今日はここまでにしましょう」「次回のMTGで」
- 「質問は後ほど」「今はここまで」「打ち合わせで決めましょう」

**この状況での正しい対応：**
1. 現時点で受け取っているすべての情報を整理・構造化して出力する（表・箇条書き）
2. 未確認事項は「打ち合わせで確認する事項リスト」として明示する（質問形式ではなく確認項目として列挙）
3. 次のSTEPへの準備完了を宣言し、クライアントの準備ができ次第進める姿勢を示す
4. 絶対に追加の質問を投げない

**クライアントの会話フロー指示は、スキルのSTEP進行指示より常に優先する。**

---

### 8. 出力フォーマット厳守（最優先ルール）

**スキルモードで動作している場合、出力の冒頭に会話的な前置きを絶対に含めない。**

各STEPの出力は、テンプレートの最初のMarkdown要素（`#`、`##`、`-`、`|` 等）から直接始める。

**禁止（冒頭に付けない）：** 「ありがとうございます」「了解です」「承知しました」「情報を整理します」などの会話的前置き

**正しい出力：** テンプレートの `##` や `|` から直接開始する

**理由：** スキルの出力は `outputMarkdown` としてDBに保存され、プロジェクト管理ドキュメントとして表示される。

---

# 統合設計スキル

実装は全部完了した。しかしブランチが多数あって、それぞれが同じファイルを変更している。マージしたら動かなくなった——これが統合の典型的な失敗だ。

このスキルは「どの順番で・どのルールで・何を確認しながらマージするか」を設計する。N 並列 Claude Code セッション × N CI gate auto-merge 前提で、Wave 単位の完了集計と Phase gate 機械判定が主軸。

**上流／下流：**
- distributed-dev で各ブランチに実装完了
- test-verification で品質基準クリア
- → このスキルで全ブランチを本体に安全に統合
- → delivery へ

---

## 絶対ルール

**STEP 1の確認ブロックを出力したら、必ずそこで止まること。**

ユーザーが「STEP 2へ」と指示するまで、絶対に次のSTEPに進んではならない。

---

## 最上位ルール

止まることがこのスキルの最も重要な動作である。確認ブロックを出力したら即停止。「STEP 2へ」の返答を待つ。

## v3 必須ルール

詳細: `references/v3-core.md`
プロジェクト固有値の適用例: `references/profiles/build-factory.md` (例として位置づけ。他プロジェクトは独自 profile を作成する)

1. **Wave 単位で集計** — 個別ブランチではなく Wave 単位 (W0/W1/.../W<N>) で auto-merged / retried / escalated / rolled-back / drift 件数を **Foundation/Backend/UI/Polish のカテゴリ別** に集計
2. **N CI gate auto-merge 前提 (project-defined)** — 各 task は gate 全 pass で機械的に merge 済。integration スキルは Wave 完了時の集計 + Phase gate 判定 + drift fix の流し込みが主軸
3. **work-package boundary (file mutex) で conflict 事前防止** — 発生は v3 仕様違反 (mutex check 漏れ) として原因記録し、tickets schema の work_package_boundary を修正
4. **Phase gate 判定は mechanical / observable** — Foundation completion → Backend completion → UI completion → Polish completion を `<phase_gate_checker>` 系 tool の exit code で判定
5. **drift fix は project-defined drift fix queue (group naming は project ごと) に流す** — lint 違反 → `<drift_ticket_generator>` → 次 Wave の drift fix group に追加
6. **rollback は task 単位 PR revert** — ブランチ単位 reset --hard は禁止 (N 並列で他 task に影響)
7. **distributed-dev + schedule-design + test-verification の出力を必ず pull** — branch-package.json N 件 / wave-schedule.json / gate-config.yml

---

## テンプレートファイル（assets/）
- `assets/merge-script-template.sh` — 統合マージ実行スクリプト（squash merge・コンフリクト検出・ドライラン対応）
- `assets/pr-template.md` — GitHub PRテンプレート（.github/pull_request_template.mdとして配置）

STEP 2（マージ戦略確定）後、merge-script-template.shにSTEP 1で決定したマージ順序を記入して実行する。pr-template.mdはリポジトリの.github/ディレクトリに配置してチーム全体で使用する。

---

## STEP 1: 統合状況の把握 (v3: Wave 単位 + 上流出力 pull + auto-merge 集計)

**このSTEPでやること：**
**Wave 単位** で何件の task が・どの状態 (auto-merged / retried / escalated / rolled-back) で・どんな drift を残しているかを集計する。個別ブランチ単位ではなく **Wave 単位** に集約するのが v3。さらに各 task が Foundation / Backend / UI / Polish のどのカテゴリの deliverable かを分けて件数集計する。

**v3 必須**: 上流出力の path を確認:

```
## 入力情報の確認 (v3)

### 上流出力
- distributed-dev: <branch_packages_dir>/*.json (各 task の branch-package.json N 件)
- schedule-design: <schedule_dir>/wave-schedule.json
- test-verification: <test_verification_dir>/gate-config.yml
- GitHub: PR list + CI status + auto-merge 状態

### 対象 Wave
- wave_id: W<N>
- phase_id: <phase_id> (project-defined: foundation / backend / ui / polish 等)
- task 件数: <N>
- カテゴリ内訳 (project-defined naming):
  - Foundation deliverable: <件数>
  - Backend deliverable: <件数>
  - UI deliverable: <件数>
  - Polish deliverable: <件数>
  - Drift fix queue: <件数>
```

**確認すること（曖昧なら【仮説】を立てて質問）：**

1. **ブランチ一覧と状態** — 何本あるか？全部実装完了か？CIパス済みか？
2. **依存関係** — 「AをマージしてからでないとBがコンパイルできない」ような順序制約はあるか？(Foundation→Backend→UI→Polish の順序遵守を確認)
3. **変更の重複** — 複数のブランチが同じファイルを変更しているか？
4. **ベースブランチの状態** — main / develop は最新か？ブランチ作成後にベースが進んでいないか？
5. **マージ方針** — squash merge / merge commit / rebase のどれを使うか？(v3 では squash merge 固定推奨)
6. **ロールバック手順** — 統合後に問題が出た場合の戻し方は？

**Webリサーチ（必要に応じてSTEP 1で実施）：**
コンフリクトが複雑な場合や、マージ戦略に迷う場合に調査する：
- 使用するGitワークフロー（GitHub Flow / GitFlow / Trunk Based）のベストプラクティス
- squash merge vs merge commit の判断基準事例

調査結果はデータ蓄積JSONの `research` フィールドに保存。

**出力形式 (v3 / Wave 集計)：**

```
## 統合状況 (v3 / Wave 単位 / Foundation→Backend→UI→Polish カテゴリ別)

### Wave 概要
- wave_id: W<N>
- phase_id: <project-defined>
- 期間: YYYY-MM-DD 〜 YYYY-MM-DD
- 並列セッション数: <N> (project-defined parallel capacity)
- task 件数: <N>
- カテゴリ内訳: Foundation=<N> / Backend=<N> / UI=<N> / Polish=<N> / Drift fix=<N>

### auto-merge 集計 (v3 / 4 カテゴリ × deliverable category)
| 状態 | Foundation | Backend | UI | Polish | Drift fix | 合計 |
|------|-----------|---------|----|----|--------|-----|
| auto-merged (N gate green) | <N> | <N> | <N> | <N> | <N> | <N> |
| retried (1〜2 失敗で recovery) | <N> | <N> | <N> | <N> | <N> | <N> |
| escalated (連続 N 失敗 → human) | <N> | <N> | <N> | <N> | <N> | <N> |
| rolled back (post-merge 問題) | <N> | <N> | <N> | <N> | <N> | <N> |

### conflict 検出 (v3: 仕様違反として原因追跡)
| 発生 task | conflict file | 原因 | 修正方針 |
|---|---|---|---|
| (発生時のみ) | (file mutex 漏れ) | tickets schema 修正 + revert + drift fix queue 再投入 |

### drift 検出 (drift fix queue 行き)
| rule_id | 件数 | 生成 drift task |
|---------|------|----------------|
| <rule_id_1> | <N> | T-DRIFT-W<N>-01〜0N |
| <rule_id_2> | <N> | T-DRIFT-W<N>-0N |

### 統合先 git state
- main HEAD: <sha>
- 取り込み済 commit: <N>
- 全 N gate (project-defined): green
```

---

**STEP 1 確認**

統合状況を確認してください。

- 競合リスクの評価は実際と合っていますか？
- マージ順序に問題はありますか？
- Foundation/Backend/UI/Polish カテゴリ別の集計に違和感はありませんか？
- 問題なければ「STEP 2へ」とお知らせください

**※ STEP 2には進まない。ユーザーの確認を待つ。**

---

## STEP 2: マージ戦略・コンフリクト原因追跡・drift 流し込み (v3)

**このSTEPでやること：**
**v3 では各 task が N CI gate auto-merge で機械的に merge されるため**、マージ戦略の設計は不要。代わりに以下を設計:
- **conflict 発生時の原因追跡フロー** (file mutex 漏れ → boundary 設計修正 → revert → drift task 再投入)
- **drift fix の queue 流し込み** (lint 違反 → `<drift_ticket_generator>` → 次 Wave の drift fix group)
- **rollback フロー** (task 単位 PR revert / ブランチ単位 reset --hard は禁止)

**マージ方法 (v3 固定)**:
- **squash merge** (`gh pr merge --auto --squash`) — Claude Code が auto-merge job で機械実行
- merge commit / rebase は使わない (N 並列で履歴が破綻するため)

**出力形式 (v3)：**

```
## マージ戦略 (v3 / auto-merge 前提)

### マージ方法
- squash merge 固定 (`gh pr merge --auto --squash`)
- Claude Code が CI gate auto-merge job で機械実行
- merge commit / rebase は使用しない

### conflict 原因追跡フロー (v3 / 仕様違反扱い)
v3 では work-package boundary (file mutex) で conflict が事前防止される前提:
1. **conflict 発生 = v3 仕様違反**: <mutex_checker> の漏れを意味する
2. **原因調査**:
   - 同 Wave 内に同一 file への editable task が複数 含まれていないか
   - shared_no_concurrent_edit の宣言漏れがないか
3. **boundary 設計修正**: tickets schema の work_package_boundary を更新
4. **revert**: 該当 task の PR を revert (`gh pr create --base main --head revert/<task_id>`)
5. **drift task 再投入**: <drift_ticket_generator> で `T-<task_id>-REDO` を生成 → 次 Wave drift fix queue に追加

### drift fix queue 流し込みフロー (v3)
1. Wave 完了時に lint 違反検出 (<wave_integration_reporter>)
2. 違反箇所ごとに drift task を自動生成 (T-DRIFT-W<N>-<seq>)
3. tickets schema に追加 + 次 Wave (W<N+1>) の drift fix group 候補リストへ
4. schedule-design.wave-schedule.json を更新 (drift fix group 割当 % は project-defined)

### rollback (v3 / task 単位)
\`\`\`bash
# task 単位 PR revert
gh pr create --base main --head revert/<task_id> \\
  --title "revert: <task_id> (post-merge issue)" \\
  --body "Reverts #<PR>. See <wave_integration_report_path>"
gh pr merge revert/<task_id> --auto --squash

# drift task を次 Wave drift fix queue に追加
<drift_ticket_generator> --task <task_id>-REDO --target-wave W<N+1>
\`\`\`

### 禁止操作 (v3)
- `git reset --hard` (N 並列で他 task に影響)
- `git revert -m 1 <merge-commit>` (squash merge では使えない)
- ブランチ単位 force push (auto-merge 中の PR を破壊)
```

---

**STEP 2 確認**

マージ戦略を確認してください。

- マージ方法の選択は適切ですか？
- コンフリクト発生時の判断基準は明確ですか？
- 問題なければ「STEP 3へ」とお知らせください

**※ STEP 3には進まない。ユーザーの確認を待つ。**

---

## STEP 3: Phase gate 開放判定 (v3 / mechanical / observable / Foundation→Backend→UI→Polish)

**このSTEPでやること：**
Wave 完了の集計を踏まえて、**Phase gate の開放判定** を mechanical / observable な条件で行う。各 Phase 移行は **Foundation completion → Backend completion → UI completion → Polish completion** の汎用フローに沿う:

| Phase 移行 (汎用) | 判定基準 (汎用) | tool (project-defined) |
|---|---|---|
| **Foundation completion → Backend phase 開始** | N CI gate 全 green + lint 違反 0 件 + AC validator pass | `<phase_gate_checker> --phase foundation` |
| **Backend completion → UI phase 開始** | Backend slice 全 merge + contract test pass + access control matrix pass | `<phase_gate_checker> --phase backend` |
| **UI completion → Polish phase 開始** | UI slice 全 merge + visual regression pass + a11y check pass + drift 累積 0 | `<phase_gate_checker> --phase ui` |
| **Polish completion → Release** | performance budget 内 + security audit pass + SLA target 達成 + docs ready | `<release_readiness_checker>` |

注: Phase 名称は project-defined (例: foundation/backend/ui/polish の代わりに alpha/beta/rc/ga 等)。`references/profiles/<project>.md` に project ごとのマッピングを記載。

**出力形式 (v3)：**

```
## Phase gate 判定 (v3 / Foundation→Backend→UI→Polish)

### 評価対象 phase_transition
- 例: Foundation completion → Backend phase 開始 (project-defined naming)

### 判定基準と evidence
| 基準 | 状態 | evidence (検証 tool 出力) |
|------|------|-----------------------|
| N CI gate 全 green | green | last <N> commits 全 pass |
| lint 違反 0 件 | 0 violations | <lint_runner> exit 0 |
| AC validator pass | pass | <ac_validator> exit 0 |

### 判定結果
- decision: OPEN_GATE / PENDING / BLOCKED
- 理由: (mechanical の場合は tool exit code を引用)
- block_release_until: (BLOCKED の場合のみ残課題)
- next_wave: W<N+1>
- approver: automated (mechanical gate) / human (Release のみ)

### 発見されたバグの扱い (Release 時のみ)
- 致命的 (P0): リリースブロック → 即修正
- 重要 (P1): リリース判断を要確認
- 軽微 (P2): 次 Wave 対応でリリース可
```

---

**STEP 3 確認**

統合後の最終確認を確認してください。

- リリース判断基準に漏れはありますか？
- Foundation/Backend/UI/Polish の各 completion gate に必要な mechanical 条件は揃っていますか？
- 問題なければ「STEP 4へ」とお知らせください

**※ STEP 4には進まない。ユーザーの確認を待つ。**

---

## STEP 4: 最終出力 (v3 / 4 形式同時出力)

「STEP 4 へ」の指示を受けたら、以下 4 形式 (2 既存 + 2 v3 新規) を一度に出力する。

### 出力① 統合計画書（Markdown）

```markdown
# 統合計画書 (v3)

## Wave 集計サマリー (Foundation/Backend/UI/Polish カテゴリ別)
## マージ戦略 (auto-merge 前提)
## conflict 原因追跡フロー
## drift fix queue 流し込み
## Phase gate 判定基準 (Foundation→Backend→UI→Polish)
## rollback 手順 (task 単位)
```

### 出力② 統合管理 JSON

```json
{
  "version": "v3",
  "project_id": "",
  "integration": {
    "merge_strategy": "squash auto-merge",
    "wave_id": "W<N>",
    "phase_id": "<project-defined>",
    "post_merge_checks": ["N CI gate", "<wave_integration_reporter>"],
    "rollback_plan": "task 単位 PR revert + drift fix queue Wave 再起動"
  },
  "status": "ready",
  "next_skill": "delivery"
}
```

### 出力③ wave-integration-report.md (v3 新規 / Wave 完了集計)

```markdown
# Wave Integration Report: W<N>

## 概要
- wave_id: W<N>
- phase_id: <project-defined>
- 期間: YYYY-MM-DD 〜 YYYY-MM-DD
- 並列セッション数: <N>
- task 件数: <N>
- カテゴリ内訳: Foundation=<N> / Backend=<N> / UI=<N> / Polish=<N> / Drift fix=<N>

## auto-merge 集計 (4 カテゴリ × deliverable category)
| 状態 | Foundation | Backend | UI | Polish | Drift fix | 合計 |
|------|-----------|---------|----|----|--------|-----|
| auto-merged | <N> | <N> | <N> | <N> | <N> | <N> |
| retried | <N> | <N> | <N> | <N> | <N> | <N> |
| escalated | <N> | <N> | <N> | <N> | <N> | <N> |
| rolled back | <N> | <N> | <N> | <N> | <N> | <N> |

## 連続失敗の原因分析
- T-XXX-XX: gate #<N> <gate_name> N 連続失敗
  - 原因: <root cause>
  - 対応: pre-flight audit MD に追記、distributed-dev で再起動

## drift 検出 (drift fix queue 行き)
| rule_id | 件数 | 修正 task |
|---------|------|----------|
| <rule_id_1> | <N> | T-DRIFT-W<N>-01〜0N |
| <rule_id_2> | <N> | T-DRIFT-W<N>-0N |

→ 次 Wave (W<N+1>) の drift fix group に追加。

## 統合先 git state
- main HEAD: <sha>
- 取り込み済 commit: <N>
- 全 N gate: green
```

### 出力④ phase-gate-decision.json (v3 新規 / Phase ゲート判定)

```json
{
  "version": "v3",
  "skill": "integration",
  "decisions": [
    {
      "phase_transition": "Foundation completion → Backend phase",
      "evaluated_at": "YYYY-MM-DDTHH:MM:SSZ",
      "criteria": [
        {"name": "N CI gate", "status": "green", "evidence": "all gates passed for last N commits"},
        {"name": "lint", "status": "0 violations", "evidence": "<lint_runner> exit 0"},
        {"name": "AC validator", "status": "pass", "evidence": "<ac_validator> exit 0"}
      ],
      "decision": "OPEN_GATE",
      "block_release_until": null,
      "next_wave": "W<N+1>",
      "approver": "automated (mechanical gate)"
    },
    {
      "phase_transition": "Backend completion → UI phase",
      "evaluated_at": null,
      "criteria": [],
      "decision": "PENDING",
      "block_release_until": "<remaining work description>",
      "next_wave": "W<N+M>",
      "approver": null
    }
  ]
}
```

---

## 構造化JSON出力仕様（最終ステップのみ）

```devos-json
{
  "items": [
    {
      "id": "INT-001",
      "name": "統合項目名",
      "description": "説明",
      "status": "pending",
      "dependencies": [],
      "assignee": "",
      "estimated_hours": 4,
      "test_criteria": ["テスト基準1"],
      "risks": []
    }
  ],
  "test_plan": [
    {"type": "統合テスト", "scope": "APIエンドポイント全体", "tools": ["Jest", "Supertest"]}
  ],
  "go_live_criteria": ["全テストパス", "ステージング環境確認"],
  "rollback_plan": "ロールバック手順の説明"
}
```
