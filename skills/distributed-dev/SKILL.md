---
name: distributed-dev
description: タスク分解スキルで作成したタスクカードを、Claude Code が単独で実装できる「ブランチ実装パッケージ」に変換するスキル。ブランチ名 / CLAUDE.md / 環境設定 / スコープ境界 / Done Criteria を生成し、開発者が「進めて」と言うだけで Claude Code が自走できる状態を作る。**v3 採用 (2026-05-15〜)**: **task-decomposition の tickets.json (3-tier AC + work_package_boundary) と api-design の ears-ac-seed.json と schedule-design の wave-schedule.json を pull** し、CLAUDE.md に **3-tier AC (structural/functional/regression)** + **upstream 成果物 path (mock_path / openapi.yaml / entities.json / EARS AC)** + **Wave ID + 並列起動順 + depends_on_waves + parallel_session_count_target** + **pre-flight audit MD path** を必ず埋め込む。Done Criteria には **8 CI gate auto-merge** (lint-mock / AC validator / RLS coverage / audit MD / pytest cov ≥70% / pyright / tsc / mock-impl-diff 全 pass で PR を Claude が自動 merge / 連続 3 失敗で human エスカ) を必須記載。work-package boundary を **file-level mutex** (editable / shared_no_concurrent_edit / readonly / forbidden の 4 区分) として明示し、Wave 内並列セッション競合を機械的に防ぐ。task 着手前に **pre-flight audit MD** を template から生成して埋めてから実装開始 (事後監査ループを廃止)。Claude Code に実装させたい・ブランチを切って渡したい・実装者に情報を最小限だけ渡したい・監視役として進めたい・30-50 並列で起動したい・3-tier AC を CLAUDE.md に埋めたい・8 CI gate を Done Criteria に含めたい・work-package boundary を file mutex で明示したい・pre-flight audit MD を生成したい・wave-schedule.json から Wave 起動順を継承したい・start-cmd.sh / done-cmd.sh を出したい場面で必ず使うこと。4STEP の対話型プロセスで進み、出力はブランチ作業手順 (Markdown) + CLAUDE.md (Claude Code 指示書) + 管理 JSON + **audit-md-template.md** (pre-flight 監査テンプレ) + **start-cmd.sh / done-cmd.sh** (起動・完了スクリプト) の **5 形式**。
tab: 品質・運用
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

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

❌ 悪い仮説：「売上を増やしたい」「効率化したい」（汎用すぎて意味がない）

✅ 良い仮説の構造：
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

❌ **禁止（冒頭に付けない）：** 「ありがとうございます」「了解です」「承知しました」「情報を整理します」などの会話的前置き

✅ **正しい出力：** テンプレートの `##` や `|` から直接開始する

**理由：** スキルの出力は `outputMarkdown` としてDBに保存され、プロジェクト管理ドキュメントとして表示される。

---

# ブランチ実装パッケージ設計スキル

**このスキルが作るもの：**
各タスクに対して「ブランチ名 + CLAUDE.md」のセットを生成する。
開発者はブランチを切り、CLAUDE.mdを置き、Claude Codeを起動して「進めて」と言うだけでよい。

**前提となる全体フロー：**
```
⑨ スケジュール設計完了
    ↓
⑩ このスキル（タスクごとにブランチ実装パッケージを作成）
    ↓
各ブランチでClaude Codeが自走実装
    ↓
開発者が統合・マージ（⑪統合スキル）
```

**情報分離の設計思想：**
各ブランチのClaude Codeは「このファイルを作り、この動作を実現する」ことしか知らない。
クライアント名・サービス全体像・他タスクの存在・プロジェクト名は渡さない。
「工場の作業員」として、指示された部品だけを正確に作る。

---

## ⛔ 絶対ルール

**STEP 1の確認ブロックを出力したら、必ずそこで止まること。**

ユーザーが「STEP 2へ」と指示するまで、絶対に次のSTEPに進んではならない。

---

## 最上位ルール

止まることがこのスキルの最も重要な動作である。確認ブロックを出力したら即停止。「STEP 2へ」の返答を待つ。

## v3 必須ルール (2026-05-15〜)

詳細: `references/v3-extensions.md`

1. **task-decomposition + api-design + schedule-design + test-verification の出力を必ず pull** — tickets.json (3-tier AC + work_package_boundary) / ears-ac-seed.json + openapi.yaml / wave-schedule.json (wave_id + depends_on_waves + parallel_session_count_target) / gate-config.yml + ears-test-mapping.json
2. **CLAUDE.md に 3-tier AC を逐語コピー** — Done Criteria を Tier 1 (structural / lint #17) + Tier 2 (functional / EARS + RLS + Schemathesis) + Tier 3 (regression / 8 CI gate) で構成
3. **work-package boundary を file-level mutex の 4 区分で明示** — editable / shared_no_concurrent_edit (Wave 内排他) / readonly / forbidden。違反は lint #16 で CI 検出
4. **pre-flight audit MD を着手前に必ず生成** — `docs/audit/<date>_v3/<task_id>.md` を template から作って埋めてから実装開始。事後監査ループは廃止
5. **8 CI gate auto-merge を Done Criteria に必須記載** — 全 gate green で `gh pr merge --auto --squash`。連続 3 失敗で human エスカ
6. **Wave 起動順を wave-schedule.json から継承** — wave_id / depends_on_waves / parallel_session_count_target / group (A/B/C/D) を CLAUDE.md 冒頭に必須記載

---

## STEP 1: タスクとブランチ境界の確認 (v3: 上流出力 pull + work_package_boundary)

**このSTEPでやること：**
どのタスクをどのブランチで実装するか、その境界を確定する。

**v3 必須**: 上流出力 path を確認し、work_package_boundary を 4 区分で明示:

```
## 入力情報の確認 (v3)

### 上流出力
- task-decomposition: docs/task-decomposition/<date>_v<N>/tickets.json (entry: <task_id>)
- api-design: docs/api-design/<date>_v<N>/
  - openapi.yaml (該当 path)
  - ears-ac-seed.json (該当 endpoint AC)
- functional-breakdown: docs/functional-breakdown/<date>_v<N>/
  - screens.json (該当 screen_id の mock_path / h1_text)
  - entities.json (該当 entity の rls_policies)
- schedule-design: docs/schedule-design/<date>_v<N>/wave-schedule.json (wave_id)
- test-verification: docs/test-verification/<date>_v<N>/
  - gate-config.yml (8 gate)
  - ears-test-mapping.json (test ID 対応)

### Wave 起動情報 (wave-schedule.json から継承)
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>
- group: A (Foundation) / B (Vertical Slice) / C (Integration) / D (Drift fix)

### pre-flight audit MD
- 着手前 path: docs/audit/<date>_v<N>/<task_id>.md
- template: docs/audit/<date>_v<N>/_template.md
```

**確認すること（曖昧なら【仮説】を立てて質問）：**

1. **タスクの内容** — task_id / title / 実装する機能・エンドポイントやコンポーネント名
2. **ブランチ戦略** — ベースブランチ (main / develop)。命名規則 `claude/<task_id>` を継承
3. **work-package boundary (v3 / 4 区分)**:
   - **editable**: 作成・編集してよいファイル
   - **shared_no_concurrent_edit**: Wave 内で他 task と共有、同時編集禁止 (file mutex)
   - **readonly**: 読むが変更しない
   - **forbidden**: 絶対に触らない
4. **環境設定の状態** — 開発環境は構築済みか
5. **v3: pre-flight audit MD 採用方針** — 着手前 template 埋込を必須にするか
6. **v3: Wave 起動情報の継承** — wave-schedule.json から wave_id / depends_on_waves / parallel_session_count を pull できているか
7. **v3: 情報秘匿レベル** — 内製 dogfood (Phase 1) は緩和 / 外部 SaaS (Phase 2) では再強化

**出力形式 (v3)：**

```
## タスク・ブランチ境界確認 (v3)

### タスク概要
- task_id:
- title:
- 実装内容 (1〜2 文):
- ブランチ名: claude/<task_id>

### Wave 起動情報 (wave-schedule.json から継承)
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>
- group: <A / B / C / D>

### work-package boundary (v3 / 4 区分)
| 区分 | ファイル / パス | 検証 |
|-----|--------------|------|
| editable (作成・編集 OK) | | lint #16 で diff 検証 |
| shared_no_concurrent_edit (Wave 内排他) | | check-wave-mutex.py で起動時検証 |
| readonly (読むが変更しない) | | lint #16 で diff 検証 |
| forbidden (絶対触らない) | | lint #16 で diff 検証 |

### pre-flight audit MD
- path: docs/audit/<date>_v<N>/<task_id>.md
- template: docs/audit/<date>_v<N>/_template.md
- 着手前埋め込み: 必須 (post-implementation 監査は廃止)

### 環境設定
- 事前構築済み: (はい / 【仮説】確認が必要)
- このブランチ特有のセットアップ: (なし / ある場合は内容)

### CLAUDE.md から除外する情報
- Phase 1 内製 dogfood: 秘匿緩和
- Phase 2 SaaS: クライアント名・ビジネスロジック秘匿
```

---

📦 **STEP 1 確認**

ブランチ境界を確認してください。

- ブランチ名・スコープ境界に漏れや誤りはありますか？
- 除外する情報は適切ですか？
- 問題なければ「STEP 2へ」とお知らせください

**※ STEP 2には進まない。ユーザーの確認を待つ。**

---

## STEP 2: 実装仕様の確定 (v3: EARS AC 逐語コピー + upstream path 埋め込み)

**このSTEPでやること：**
Claude Code が「何をどう作るか」を迷わないよう、CLAUDE.md の核心部分を組み立てる。

**v3 必須**:
- **CLAUDE.md '0. 上流出力' に 7 path を必ず列挙** (task / mock / api / ears_ac_seed / entities / wave / pre_flight_audit)
- **'1. Wave / 起動情報' を冒頭に必ず記載** (wave_id / depends_on_waves / parallel_session_count_target / group)
- **'4. 実装仕様 / EARS AC' に api-design の ears-ac-seed.json から逐語コピー** (EVENT-DRIVEN + UNWANTED 1 件以上)
- **型定義は openapi.yaml から自動生成 (openapi-typescript / datamodel-code-generator) を明示** (人手 edit 禁止)
- **'5. RLS policy' に entities.json から rls_policies 配列を引用**

**精緻化の方針：**
曖昧な仕様は「良い感じの実装」になる。良い感じの実装は統合時に問題を起こす。
「既存コードと同じパターンで」と言う場合、どのファイルのどのパターンかを明示する。

**出力形式：**

```
## 実装仕様

### 型定義 / インターフェース
\`\`\`typescript
// 入力
interface [InputType] { ... }
// 出力
interface [OutputType] { ... }
\`\`\`

### 処理フロー
1. （ステップ1の処理）
2. （ステップ2の処理）

### 参照すべき既存パターン
- [src/xxx/yyy.ts] の [関数名] と同じ構造で実装する

### エラーハンドリング
| エラーケース | HTTPステータス / 対応 |
|-----------|-------------------|
| バリデーションエラー | 400 |
| 認証エラー | 401 |

### 命名・コーディング規則
- 変数命名：camelCase / snake_case
- 既存ファイルの命名パターンに従う

### 絶対にやってはいけないこと
- NG: スコープ外のファイルを変更する（発見したバグはコメントとして記録するだけ）
- NG: 既存の[XXX]関数の内部を変えるリファクタリング
- NG: 仕様にない機能の追加（どんなに便利そうでも）
- NG: コードコメントや変数名にクライアント名・企業名を含める
```

---

📦 **STEP 2 確認**

実装仕様を確認してください。

- 型定義・処理フローは実際のコードベースと整合していますか？
- 「やってはいけないこと」に追加すべきことはありますか？
- 問題なければ「STEP 3へ」とお知らせください

**※ STEP 3には進まない。ユーザーの確認を待つ。**

---

## STEP 3: Done Criteria の設計 (v3: 3-tier AC + 8 CI gate + pre-flight audit MD)

**このSTEPでやること：**
Claude Code が「実装完了」と判断するための、観測可能なチェックリストを設計する。

**v3 必須**: Done Criteria を **3-tier AC (Tier 1 structural / Tier 2 functional / Tier 3 regression) + 8 CI gate auto-merge + pre-flight audit MD** で構成。

**出力形式 (v3)：**

```
## Done Criteria (v3 / 3-tier AC + 8 CI gate)

### Tier 1: Structural (mock/spec 一致)
- [ ] mock_path (<screen_id>.html) の h1_text / kpi_labels / btn_labels が実装と一致
- [ ] lint #17 mock-impl-diff: 0 件

### Tier 2: Functional (EARS API + RLS + Contract)
- [ ] EARS AC seed の全件が ears-test-mapping.json で実装され pytest pass
- [ ] verify-rls-coverage: 4 ロール (owner/admin/member/guest) × 7 操作 (SELECT own/others, INSERT, UPDATE own/others, DELETE own/others) マトリクス pass
- [ ] Schemathesis (OpenAPI fuzz) pass
- [ ] Pact contract verify pass (任意)

### Tier 3: Regression (test / lint / type / coverage / audit MD)
- [ ] pytest --cov --cov-fail-under=70 全 pass
- [ ] pyright strict: 0 error
- [ ] tsc --noEmit strict: 0 error
- [ ] lint-mock.sh: 19 check 全 pass
- [ ] validate-tickets.py: 3-tier AC schema pass
- [ ] pre-flight audit MD (docs/audit/<date>_v3/<task_id>.md) が埋まり、commit に含まれる

### 8 CI gate auto-merge (v3 必須)
| # | gate | tool | 結果 |
|---|------|------|------|
| #1 | lint-mock | scripts/lint-mock.sh | green |
| #2 | AC validator | scripts/validate-tickets.py | green |
| #3 | RLS coverage | scripts/verify-rls-coverage.py | green |
| #4 | audit MD existence | scripts/audit-md-check.sh | green |
| #5 | pytest cov ≥70% | pytest --cov --cov-fail-under=70 | green |
| #6 | pyright strict | pyright | green |
| #7 | tsc strict | tsc --noEmit | green |
| #8 | mock-impl-diff | scripts/lint-mock-impl-diff.py | green |

- 全 gate green で `gh pr merge --auto --squash`
- 連続 3 失敗で human エスカ

### work-package boundary 遵守確認
- [ ] `git diff --name-only` で変更ファイルが editable + shared_no_concurrent_edit の subset
- [ ] forbidden への変更が 0 件
- [ ] shared_no_concurrent_edit への変更は Wave mutex 取得済 (check-wave-mutex.py pass)
- [ ] スコープ外バグ発見時は修正せず `// TODO(drift): <issue>` でコメント (Group D Wave に流す)
```

---

📦 **STEP 3 確認**

Done Criteriaを確認してください。

- 全項目が観測可能な形で書かれていますか？
- 問題なければ「STEP 4へ」とお知らせください

**※ STEP 4には進まない。ユーザーの確認を待つ。**

---

## STEP 4: CLAUDE.md と実装パッケージの生成 (v3: 5 形式出力)

全STEPの確認が完了したら、以下 5 形式 (3 既存 + 2 v3 新規) を生成する。

### 出力① ブランチ作業手順（開発者向け）

```markdown
## ブランチ作業手順

\`\`\`bash
# 1. ブランチを切る
git checkout [base-branch]
git pull
git checkout -b [branch-name]

# 2. CLAUDE.mdをプロジェクトルートに配置
# （以下のCLAUDE.mdをコピー）

# 3. Claude Codeを起動して「進めて」と指示
\`\`\`
```

### 出力② CLAUDE.md (v3 / ブランチルートに置く — これが Claude Code への唯一の指示)

```markdown
# 実装タスク: <task_id> - <title>

## 0. 上流出力 (v3 / context を構成する path)
- task: docs/task-decomposition/<date>_v<N>/tickets.json (entry: <task_id>)
- mock: docs/mocks/<date>_v<N>/<screen_id>.html
- api: docs/api-design/<date>_v<N>/openapi.yaml (path: <method> <endpoint>)
- ears_ac_seed: docs/api-design/<date>_v<N>/ears-ac-seed.json (endpoint: <method> <endpoint>)
- entities: docs/functional-breakdown/<date>_v<N>/entities.json (entity: <entity_id>)
- wave: docs/schedule-design/<date>_v<N>/wave-schedule.json (wave_id: <wave_id>)
- pre_flight_audit: docs/audit/<date>_v<N>/<task_id>.md (着手前に必ず埋める)

## 1. Wave / 起動情報 (v3 / wave-schedule.json から継承)
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>
- group: <A | B | C | D>

## 2. あなたの役割
この CLAUDE.md に書かれた内容だけを実装する。
スコープ外のコードは参照してよいが、変更しない。
「良い感じに改善」は一切しない。指示された通りに作る。

## 3. work-package boundary (v3 / 4 区分の file mutex)

### editable (作成・編集 OK)
- backend/routers/auth.py
- backend/services/auth_service.py
- backend/tests/test_auth.py

### shared_no_concurrent_edit (Wave 内排他 / 同時編集禁止)
- backend/main.py
- frontend/src/types/api.ts ← openapi-typescript 自動生成、人手 edit 禁止

### readonly (読むが変更しない)
- backend/models/user.py

### forbidden (絶対触らない)
- backend/migrations/
- docs/

## 4. 実装仕様

### EARS AC (v3 / api-design ears-ac-seed.json から逐語コピー)
- EVENT-DRIVEN: When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.
- UNWANTED: If credentials are invalid, the system shall return 401 with generic message (no user enumeration).
- ...

### 型定義 (openapi.yaml から自動生成済 / 人手 edit 禁止)
```typescript
// frontend/src/api/types.ts (auto-generated by openapi-typescript)
export type LoginRequest = { email: string; password: string; mfa_code?: string };
export type LoginResponse = { access_token: string; refresh_token: string; user_id: string; mfa_required: boolean };
```

### 処理フロー
1. ...
2. ...

## 5. RLS policy (entities.json から)
- auth_sessions:user_own_select
- auth_sessions:user_own_insert

## 6. Done Criteria (v3 / 3-tier AC + 8 CI gate)
[STEP 3 のチェックリストをそのまま記載]

## 7. pre-flight audit MD (着手前に必ず実行)

```bash
cp docs/audit/<date>_v<N>/_template.md docs/audit/<date>_v<N>/<task_id>.md
# audit MD を埋める (既存実装の調査 / 3-tier AC 現状評価 / 触る予定ファイル一覧 / 実装方針)
git add docs/audit/<date>_v<N>/<task_id>.md
git commit -m "audit(pre-flight): <task_id>"
```

## 8. 完了報告の形式
Done Criteria の全項目について `✅ 確認済み: <確認方法>` の形式で報告する:

```
✅ Tier 1: lint #17 mock-impl-diff 0 件
✅ Tier 2: ears-test-mapping.json 6/6 件 pass
✅ Tier 2: RLS 4×7 マトリクス pass
✅ Tier 3: pytest cov 78% / pyright 0 error / tsc 0 error
✅ Tier 3: audit MD 埋め込み済
```

## 9. 注意事項 (機械的 boundary)
- スコープ外のファイルを変更しない (lint #16 で CI 自動検出 → reject)
- 同時編集禁止 file への push は merge conflict 必至 → 先に Wave 内 mutex 取得
- 既存関数の内部リファクタは forbidden (Phase 1.5 REFACTOR Wave で行う)
- 仕様にない機能の追加は禁止 (どんなに便利でも)
- スコープ外バグ発見時: 修正せず `// TODO(drift): <issue>` でコメント (Group D Wave に流す)
- Phase 2 SaaS 公開時: コードコメント・変数名・ログにクライアント名・企業名・サービス固有の固有名詞を入れない
```

### 出力③ 管理用 JSON (v3 / 機械処理・⑪統合スキルへの引き継ぎ用)

```json
{
  "version": "v3",
  "task_id": "",
  "branch_name": "",
  "base_branch": "main",
  "wave_id": "",
  "depends_on_waves": [],
  "parallel_session_count_target": 0,
  "group": "B",
  "work_package_boundary": {
    "editable": [],
    "shared_no_concurrent_edit": [],
    "readonly": [],
    "forbidden": []
  },
  "upstream_paths": {
    "task": "",
    "mock": "",
    "api": "",
    "ears_ac_seed": "",
    "entities": "",
    "wave": "",
    "pre_flight_audit": ""
  },
  "done_criteria_3tier": {
    "tier1_structural": [],
    "tier2_functional": [],
    "tier3_regression": []
  },
  "ci_gates": ["lint-mock", "AC-validator", "RLS-coverage", "audit-md", "pytest-cov-70", "pyright", "tsc", "mock-impl-diff"],
  "auto_merge": true,
  "consecutive_failure_threshold": 3,
  "status": "ready",
  "next_skill": "integration"
}
```

### 出力④ audit-md-template.md (v3 新規 / pre-flight 監査テンプレ)

```markdown
# audit: <task_id>

## pre-flight (着手前 / 必須)

### 既存実装の調査
- 関連 file: (grep 結果)
- 既存パターン: (どの file の何関数を参考にするか)
- 落とし穴: (既知の bug / 非互換)

### 3-tier AC の現状評価
- Tier 1 structural: 何% 満たされているか
- Tier 2 functional: 既存 endpoint で何件 pass か
- Tier 3 regression: cov / lint / type の現状値

### 触る予定ファイル
| file | 区分 (editable/shared/readonly/forbidden) | 理由 | 変更規模 |
|---|---|---|---|

### 実装方針
- alternatives: (検討した案)
- chosen: (選定理由)

## post-implementation (完了後 / 任意)

### 実装後の AC pass 状況
### drift 発見 (TODO(drift) として記録した item 一覧)
```

### 出力⑤ start-cmd.sh / done-cmd.sh (v3 新規 / 起動・完了スクリプト)

```bash
# start-cmd.sh
#!/bin/bash
set -e
TASK_ID="$1"
DATE="<date>"
VERSION="v3"

# 1. branch を切る (idempotent)
git checkout main && git pull
git checkout -b "claude/${TASK_ID,,}" 2>/dev/null || git checkout "claude/${TASK_ID,,}"

# 2. pre-flight audit MD を生成 (まだ無ければ)
AUDIT_PATH="docs/audit/${DATE}_${VERSION}/${TASK_ID}.md"
[ -f "$AUDIT_PATH" ] || cp "docs/audit/${DATE}_${VERSION}/_template.md" "$AUDIT_PATH"

# 3. Wave mutex check
python3 scripts/check-wave-mutex.py --task "$TASK_ID"

# 4. CLAUDE.md を表示
cat ".claude/branches/${TASK_ID}.md"
```

```bash
# done-cmd.sh
#!/bin/bash
set -e
TASK_ID="$1"

# 1. all 8 gates
bash scripts/lint-mock.sh
python3 scripts/validate-tickets.py
python3 scripts/verify-rls-coverage.py
bash scripts/audit-md-check.sh
pytest --cov --cov-fail-under=70
pyright
tsc --noEmit
python3 scripts/lint-mock-impl-diff.py

# 2. work-package boundary check
python3 scripts/check-work-package-boundary.py --task "$TASK_ID"

# 3. push + PR + auto-merge
git push -u origin HEAD
# (GitHub Actions が 8 gate を再実行し、全 pass で auto-merge)
```

---

## 📦 構造化JSON出力仕様（最終ステップのみ）

```devos-json
{
  "branch_strategy": "GitHub Flow",
  "branches": [
    {"name": "main", "purpose": "本番環境", "naming_convention": "-", "merge_target": "-"},
    {"name": "feature/*", "purpose": "機能開発", "naming_convention": "feature/[task-id]-[description]", "merge_target": "develop"}
  ],
  "workflow": [
    {"step": 1, "action": "featureブランチ作成", "responsible": "開発者", "criteria": "タスク開始時"}
  ],
  "review_process": {
    "required_reviewers": 1,
    "auto_checks": ["lint", "type-check", "test"],
    "merge_conditions": ["CIパス", "レビュー承認"]
  },
  "communication": [
    {"channel": "GitHub Issues", "purpose": "タスク管理", "frequency": "随時"}
  ],
  "claude_md_content": "CLAUDE.mdの内容"
}
```
