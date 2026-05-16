---
name: distributed-dev
description: タスク分解スキルで作成したタスクカードを、コーディングエージェント (Claude Code 等) が単独で実装できる「ブランチ実装パッケージ」に変換するスキル。ブランチ名 / CLAUDE.md / 環境設定 / スコープ境界 / Done Criteria を生成し、開発者が「進めて」と言うだけでエージェントが自走できる状態を作る。v3 (2026-05-15〜): tickets.json (3-tier AC + work_package_boundary) + ears-ac-seed.json + wave-schedule.json を pull し、CLAUDE.md に 3-tier AC + upstream 成果物 path + Wave ID + 並列起動順 + pre-flight audit MD path を必ず埋め込む。Done Criteria に N CI gate auto-merge を必須記載。work-package boundary を file-level mutex (editable / shared_no_concurrent_edit / readonly / forbidden) で明示し並列セッション競合を機械的に防ぐ。Wave 内も backend-first → UI-second 順序維持。task 着手前に pre-flight audit MD を template から生成して埋めてから実装開始。「コーディングエージェントに実装させたい」「ブランチを切って渡したい」「並列で起動したい」「3-tier AC を CLAUDE.md に埋めたい」「N CI gate を Done Criteria に含めたい」「work-package boundary を file mutex で明示したい」「pre-flight audit MD を生成したい」「wave-schedule.json から Wave 起動順を継承したい」「start-cmd.sh / done-cmd.sh を出したい」場面で必ず使う。4STEP の対話型プロセス。出力はブランチ作業手順 + CLAUDE.md + 管理 JSON + audit-md-template.md + start-cmd.sh / done-cmd.sh の 5 形式。
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
開発者はブランチを切り、CLAUDE.mdを置き、コーディングエージェント (Claude Code 等) を起動して「進めて」と言うだけでよい。

**前提となる全体フロー：**
```
⑨ スケジュール設計完了
    ↓
⑩ このスキル（タスクごとにブランチ実装パッケージを作成）
    ↓
各ブランチでコーディングエージェントが自走実装
    ↓
開発者が統合・マージ（⑪統合スキル）
```

**情報分離の設計思想：**
各ブランチのエージェントは「このファイルを作り、この動作を実現する」ことしか知らない。
クライアント名・サービス全体像・他タスクの存在・プロジェクト名は渡さない (秘匿が必要な場合)。
「工場の作業員」として、指示された部品だけを正確に作る。

---

## ⛔ 絶対ルール

**STEP 1の確認ブロックを出力したら、必ずそこで止まること。**

ユーザーが「STEP 2へ」と指示するまで、絶対に次のSTEPに進んではならない。

---

## 最上位ルール

止まることがこのスキルの最も重要な動作である。確認ブロックを出力したら即停止。「STEP 2へ」の返答を待つ。

## v3 必須ルール (2026-05-15〜)

詳細: `references/v3-core.md`
プロジェクト固有値の適用例: `references/profiles/build-factory.md` (例として位置づけ。他プロジェクトは独自 profile を作成する)

1. **task-decomposition + api-design + schedule-design + test-verification + functional-breakdown の出力を必ず pull** — tickets.json (3-tier AC + work_package_boundary) / ears-ac-seed.json + openapi.yaml / wave-schedule.json (wave_id + depends_on_waves + parallel_session_count_target) / gate-config.yml + ears-test-mapping.json / screens.json + entities.json
2. **CLAUDE.md に 3-tier AC を逐語コピー** — Done Criteria を Tier 1 (structural / mock-impl-diff) + Tier 2 (functional / EARS + access control matrix + contract test) + Tier 3 (regression / N CI gate) で構成
3. **work-package boundary を file-level mutex の 4 区分で明示** — editable / shared_no_concurrent_edit (Wave 内排他) / readonly / forbidden。違反は <boundary_lint_rule> で CI 検出
4. **pre-flight audit MD を着手前に必ず生成** — `<audit_dir>/<task_id>.md` を template から作って埋めてから実装開始。事後監査ループは廃止
5. **N CI gate auto-merge を Done Criteria に必須記載 (project-defined gate set)** — 全 gate green で auto-merge コマンド実行。連続 N 失敗で human エスカ
6. **Wave 起動順を wave-schedule.json から継承** — wave_id / depends_on_waves / parallel_session_count_target / group (Foundation / Backend / UI / Integration / Polish) を CLAUDE.md 冒頭に必須記載
7. **Wave 内も backend-first → UI-second 順序維持** — 同一 Wave に backend task と UI task が混在する場合、UI task の `depends_on_tasks` に backend task を含め、backend gate が通ってから UI 着手可能と pre-flight audit MD で確認

---

## STEP 1: タスクとブランチ境界の確認 (v3: 上流出力 pull + work_package_boundary)

**このSTEPでやること：**
どのタスクをどのブランチで実装するか、その境界を確定する。

**v3 必須**: 上流出力 path を確認し、work_package_boundary を 4 区分で明示:

```
## 入力情報の確認 (v3)

### 上流出力
- task-decomposition: <task_dir>/tickets.json (entry: <task_id>)
- api-design: <api_dir>/
  - openapi.yaml (該当 path)
  - ears-ac-seed.json (該当 endpoint AC)
- functional-breakdown: <fb_dir>/
  - screens.json (該当 screen_id の mock_path / h1_text)
  - entities.json (該当 entity の access_control_policies)
- schedule-design: <schedule_dir>/wave-schedule.json (wave_id)
- test-verification: <test_dir>/
  - gate-config.yml (N gate)
  - ears-test-mapping.json (test ID 対応)

### Wave 起動情報 (wave-schedule.json から継承)
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>  (project-defined parallel capacity)
- group: Foundation / Backend / UI / Integration / Polish (project-defined naming)
- layer: backend / UI (Wave 内順序判定用)

### pre-flight audit MD
- 着手前 path: <audit_dir>/<task_id>.md
- template: <audit_dir>/_template.md
```

**確認すること（曖昧なら【仮説】を立てて質問）：**

1. **タスクの内容** — task_id / title / 実装する機能・エンドポイントやコンポーネント名
2. **ブランチ戦略** — ベースブランチ (main / develop)。命名規則 (project-defined、例: `<prefix>/<task_id>`)
3. **work-package boundary (v3 / 4 区分)**:
   - **editable**: 作成・編集してよいファイル
   - **shared_no_concurrent_edit**: Wave 内で他 task と共有、同時編集禁止 (file mutex)
   - **readonly**: 読むが変更しない
   - **forbidden**: 絶対に触らない
4. **環境設定の状態** — 開発環境は構築済みか
5. **v3: pre-flight audit MD 採用方針** — 着手前 template 埋込を必須にするか
6. **v3: Wave 起動情報の継承** — wave-schedule.json から wave_id / depends_on_waves / parallel_session_count を pull できているか
7. **v3: layer 順序確認** — このタスクは backend layer か UI layer か。UI なら同一 Wave / 上流 Wave の backend task が完了 (gate pass) しているか
8. **v3: 情報秘匿レベル** — 内製 phase は緩和 / 外部公開 phase では再強化 (project-defined naming)

**出力形式 (v3)：**

```
## タスク・ブランチ境界確認 (v3)

### タスク概要
- task_id:
- title:
- 実装内容 (1〜2 文):
- ブランチ名: <prefix>/<task_id>
- layer: backend / UI

### Wave 起動情報 (wave-schedule.json から継承)
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>
- group: <Foundation / Backend / UI / Integration / Polish>

### work-package boundary (v3 / 4 区分)
| 区分 | ファイル / パス | 検証 |
|-----|--------------|------|
| editable (作成・編集 OK) | | <boundary_lint_rule> で diff 検証 |
| shared_no_concurrent_edit (Wave 内排他) | | <wave_mutex_check> で起動時検証 |
| readonly (読むが変更しない) | | <boundary_lint_rule> で diff 検証 |
| forbidden (絶対触らない) | | <boundary_lint_rule> で diff 検証 |

### pre-flight audit MD
- path: <audit_dir>/<task_id>.md
- template: <audit_dir>/_template.md
- 着手前埋め込み: 必須 (post-implementation 監査は廃止)
- layer-aware 項目: foundation prerequisite passed? / backend gate passed? / UI 着手可能?

### 環境設定
- 事前構築済み: (はい / 【仮説】確認が必要)
- このブランチ特有のセットアップ: (なし / ある場合は内容)

### CLAUDE.md から除外する情報
- 内製 phase: 秘匿緩和
- 外部公開 phase: クライアント名・ビジネスロジック秘匿
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
コーディングエージェントが「何をどう作るか」を迷わないよう、CLAUDE.md の核心部分を組み立てる。

**v3 必須**:
- **CLAUDE.md '0. 上流出力' に 7 path を必ず列挙** (task / mock / api / ears_ac_seed / entities / wave / pre_flight_audit)
- **'1. Wave / 起動情報' を冒頭に必ず記載** (wave_id / depends_on_waves / parallel_session_count_target / group / layer)
- **'4. 実装仕様 / EARS AC' に api-design の ears-ac-seed.json から逐語コピー** (EVENT-DRIVEN + UNWANTED 1 件以上)
- **型定義は openapi.yaml から自動生成 (openapi-typescript / datamodel-code-generator) を明示** (人手 edit 禁止)
- **'5. access control policy' に entities.json から policies 配列を引用** (RLS / RBAC / policy framework の何れか)

**精緻化の方針：**
曖昧な仕様は「良い感じの実装」になる。良い感じの実装は統合時に問題を起こす。
「既存コードと同じパターンで」と言う場合、どのファイルのどのパターンかを明示する。

**Foundation → Backend → UI 順序の徹底**:
- backend layer の task: API + service + entity + access control + contract test を実装
- UI layer の task: backend gate pass を pre-flight audit MD で確認してから着手
- foundation layer (CI/CD / test infra / access control framework) はすべての backend / UI task の prerequisite

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
- NG: コードコメントや変数名にクライアント名・企業名を含める (秘匿モード時)
- NG: backend layer 完了前に UI layer の実装着手 (Wave 内順序違反)
```

---

📦 **STEP 2 確認**

実装仕様を確認してください。

- 型定義・処理フローは実際のコードベースと整合していますか？
- 「やってはいけないこと」に追加すべきことはありますか？
- 問題なければ「STEP 3へ」とお知らせください

**※ STEP 3には進まない。ユーザーの確認を待つ。**

---

## STEP 3: Done Criteria の設計 (v3: 3-tier AC + N CI gate + pre-flight audit MD)

**このSTEPでやること：**
コーディングエージェントが「実装完了」と判断するための、観測可能なチェックリストを設計する。

**v3 必須**: Done Criteria を **3-tier AC (Tier 1 structural / Tier 2 functional / Tier 3 regression) + N CI gate auto-merge + pre-flight audit MD** で構成。

**出力形式 (v3)：**

```
## Done Criteria (v3 / 3-tier AC + N CI gate)

### Tier 1: Structural (mock/spec 一致)
- [ ] mock_path (<screen_id>) の h1_text / kpi_labels / btn_labels が実装と一致
- [ ] <mock_impl_diff> rule: 0 件

### Tier 2: Functional (EARS API + access control + Contract)
- [ ] EARS AC seed の全件が ears-test-mapping.json で実装され test pass
- [ ] <access_control_verifier>: ロール × 操作 マトリクス pass (RLS / RBAC / policy framework)
- [ ] OpenAPI fuzz (Schemathesis 等) pass
- [ ] Consumer-driven contract verify (Pact 等) pass (任意)

### Tier 3: Regression (test / lint / type / coverage / audit MD)
- [ ] backend test --cov --cov-fail-under=<coverage_threshold> 全 pass
- [ ] backend type checker strict: 0 error
- [ ] frontend type checker strict: 0 error
- [ ] <lint_runner>: project-defined check 全 pass
- [ ] <ac_validator>: 3-tier AC schema pass
- [ ] pre-flight audit MD (<audit_dir>/<task_id>.md) が埋まり、commit に含まれる

### Wave 内 layer 順序チェック (v3)
- [ ] このタスクが UI layer の場合、依存する backend task の gate がすべて green
- [ ] foundation layer の前提 (CI/CD / test infra / access control framework) が稼働中

### N CI gate auto-merge (v3 必須 / project-defined gate set)
| # | gate | tool | 結果 |
|---|------|------|------|
| #1 | <lint_runner> | (project-defined) | green |
| #2 | <ac_validator> | (project-defined) | green |
| #3 | <access_control_verifier> | (project-defined) | green |
| #4 | <audit_md_check> | (project-defined) | green |
| #5 | backend test cov ≥ <threshold> | (project-defined) | green |
| #6 | backend type checker strict | (project-defined) | green |
| #7 | frontend type checker strict | (project-defined) | green |
| #N | <mock_impl_diff> | (project-defined) | green |

- 全 gate green で auto-merge コマンド実行
- 連続 N 失敗で human エスカ

### work-package boundary 遵守確認
- [ ] `git diff --name-only` で変更ファイルが editable + shared_no_concurrent_edit の subset
- [ ] forbidden への変更が 0 件
- [ ] shared_no_concurrent_edit への変更は Wave mutex 取得済 (<wave_mutex_check> pass)
- [ ] スコープ外バグ発見時は修正せず `// TODO(drift): <issue>` でコメント (Drift fix Wave に流す)
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

# 3. コーディングエージェントを起動して「進めて」と指示
\`\`\`
```

### 出力② CLAUDE.md (v3 / ブランチルートに置く — これがエージェントへの唯一の指示)

```markdown
# 実装タスク: <task_id> - <title>

## 0. 上流出力 (v3 / context を構成する path)
- task: <task_dir>/tickets.json (entry: <task_id>)
- mock: <mock_dir>/<screen_id>
- api: <api_dir>/openapi.yaml (path: <method> <endpoint>)
- ears_ac_seed: <api_dir>/ears-ac-seed.json (endpoint: <method> <endpoint>)
- entities: <fb_dir>/entities.json (entity: <entity_id>)
- wave: <schedule_dir>/wave-schedule.json (wave_id: <wave_id>)
- pre_flight_audit: <audit_dir>/<task_id>.md (着手前に必ず埋める)

## 1. Wave / 起動情報 (v3 / wave-schedule.json から継承)
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>  (project-defined parallel capacity)
- group: <Foundation | Backend | UI | Integration | Polish>
- layer: backend / UI

## 2. あなたの役割
この CLAUDE.md に書かれた内容だけを実装する。
スコープ外のコードは参照してよいが、変更しない。
「良い感じに改善」は一切しない。指示された通りに作る。
Wave 内 layer 順序: backend layer 完了後に UI layer 着手可能。

## 3. work-package boundary (v3 / 4 区分の file mutex)

### editable (作成・編集 OK)
- (project-defined)

### shared_no_concurrent_edit (Wave 内排他 / 同時編集禁止)
- (project-defined) ← 自動生成 file は人手 edit 禁止

### readonly (読むが変更しない)
- (project-defined)

### forbidden (絶対触らない)
- (project-defined)

## 4. 実装仕様

### EARS AC (v3 / api-design ears-ac-seed.json から逐語コピー)
- EVENT-DRIVEN: When <event>, the system shall <response>.
- UNWANTED: If <unwanted>, the system shall not <unwanted action>.
- ...

### 型定義 (openapi.yaml から自動生成済 / 人手 edit 禁止)
```typescript
// (auto-generated, do not edit)
export type RequestType = { ... };
export type ResponseType = { ... };
```

### 処理フロー
1. ...
2. ...

## 5. access control policy (entities.json から)
- <entity>:<policy_name>
- ...

## 6. Done Criteria (v3 / 3-tier AC + N CI gate)
[STEP 3 のチェックリストをそのまま記載]

## 7. pre-flight audit MD (着手前に必ず実行)

```bash
cp <audit_dir>/_template.md <audit_dir>/<task_id>.md
# audit MD を埋める (既存実装の調査 / 3-tier AC 現状評価 / 触る予定ファイル一覧 /
#                    Wave 内 layer 順序確認 / 実装方針)
git add <audit_dir>/<task_id>.md
git commit -m "audit(pre-flight): <task_id>"
```

## 8. 完了報告の形式
Done Criteria の全項目について `✅ 確認済み: <確認方法>` の形式で報告する:

```
✅ Tier 1: <mock_impl_diff> 0 件
✅ Tier 2: ears-test-mapping.json N/N 件 pass
✅ Tier 2: access control matrix pass
✅ Tier 3: backend test cov XX% / type checker 0 error / frontend type checker 0 error
✅ Tier 3: audit MD 埋め込み済
✅ Wave 内順序: backend gate pass 確認済 (UI layer の場合)
```

## 9. 注意事項 (機械的 boundary)
- スコープ外のファイルを変更しない (<boundary_lint_rule> で CI 自動検出 → reject)
- 同時編集禁止 file への push は merge conflict 必至 → 先に Wave 内 mutex 取得
- 既存関数の内部リファクタは forbidden (Polish phase で行う)
- 仕様にない機能の追加は禁止 (どんなに便利でも)
- スコープ外バグ発見時: 修正せず `// TODO(drift): <issue>` でコメント (Drift fix Wave に流す)
- 公開 phase: コードコメント・変数名・ログにクライアント名・企業名・サービス固有の固有名詞を入れない
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
  "group": "Backend",
  "layer": "backend",
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
  "ci_gates": [],
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

### Wave 内 layer 順序チェック (v3)
- foundation prerequisite passed? (Y/N + 根拠)
- backend gate passed? (Y/N + 根拠 / UI layer の場合は必須)
- UI 着手可能? (Y/N / UI layer の場合)

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
git checkout -b "<prefix>/${TASK_ID,,}" 2>/dev/null || git checkout "<prefix>/${TASK_ID,,}"

# 2. pre-flight audit MD を生成 (まだ無ければ)
AUDIT_PATH="<audit_dir>/${TASK_ID}.md"
[ -f "$AUDIT_PATH" ] || cp "<audit_dir>/_template.md" "$AUDIT_PATH"

# 3. Wave mutex check
<wave_mutex_check> --task "$TASK_ID"

# 4. CLAUDE.md を表示
cat ".claude/branches/${TASK_ID}.md"
```

```bash
# done-cmd.sh
#!/bin/bash
set -e
TASK_ID="$1"

# 1. all N gates (project-defined gate set)
<lint_runner>
<ac_validator>
<access_control_verifier>
<audit_md_check>
<backend_test> --cov --cov-fail-under=<threshold>
<backend_type_checker>
<frontend_type_checker>
<mock_impl_diff>

# 2. work-package boundary check
<work_package_boundary_check> --task "$TASK_ID"

# 3. push + PR + auto-merge
git push -u origin HEAD
# (CI runner が N gate を再実行し、全 pass で auto-merge)
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
