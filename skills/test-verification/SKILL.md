---
name: test-verification
description: 実装完了したコードのテスト戦略設計・品質検証スキル。何をどのレベルでテストするか、テスト種類の選定 (unit / integration / E2E / contract / access-control matrix)、カバレッジ基準、CI 連携、受け入れ基準を設計する。**v3 採用 (2026-05-15〜)**: **task-decomposition の tickets.json (3-tier AC) と api-design の ears-ac-seed.json を pull** し、**3-tier AC を test レベルに 1:1 マッピング** (structural → mock-impl-diff lint / functional → unit+contract+access-control / regression → CI gate 自動化)。**EARS 形式 AC から test case 自動生成** (EVENT-DRIVEN → 正常系 / UNWANTED → 異常系 / STATE-DRIVEN → parametrize)。**N CI gate (project-defined, e.g., 5-10)** を Foundation gate (lint / format / AC validator) → Backend gate (access-control coverage / API contract / coverage threshold) → UI gate (type check / mock-impl drift / visual regression) → Polish gate (audit MD / perf / sec) の段階で構成。**Access control matrix test (role × operation, project-defined roles e.g., 3-10 × operations e.g., 5-8)** を access-control verifier で網羅。Schemathesis (OpenAPI → fuzz) + Pact (frontend ↔ backend consumer/provider) を contract test に採用。連続 N 失敗で human エスカ、全 pass で auto-merge。テストを書きたい・テスト戦略を決めたい・品質基準を設けたい・CI を整備したい・リグレッションを防ぎたい・3-tier AC を test に落としたい・EARS AC から test を生成したい・access-control を role × operation matrix でテストしたい・N CI gate を段階構成したい・mock-impl drift を防ぎたい・Schemathesis/Pact を contract test に使いたい・gate-config.yml を作りたい・ears-test-mapping.json を作りたいといった場面で必ず使うこと。4STEP の対話型プロセスで進み、出力はテスト計画書 (Markdown) + テスト設計 JSON + **gate-config.yml** (CI gate 設定) + **ears-test-mapping.json** (EARS AC ↔ test ID 対応) の **4 形式**。
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

# テスト・品質検証設計スキル

実装が完了してもテストがなければ「動く」かどうかわからない。テストがあっても設計が悪ければ、本番で壊れる変更がすり抜ける。

このスキルは「何をどのレベルでテストするか」を設計する。コードを書く前に設計できれば理想的だが、実装後でも遅くない。

**このスキルの位置づけ：**
- 並列実装された各ブランチの品質を統一基準で検証する
- 統合の前に「マージしてよい品質かどうか」を判断する基準を作る
- Done Criteria を test で自動化することで「完成しました」の言葉を不要にする

---

## ⛔ 絶対ルール

**STEP 1の確認ブロックを出力したら、必ずそこで止まること。**

ユーザーが「STEP 2へ」と指示するまで、絶対に次のSTEPに進んではならない。

---

## 最上位ルール

止まることがこのスキルの最も重要な動作である。確認ブロックを出力したら即停止。「STEP 2へ」の返答を待つ。

## v3 必須ルール (2026-05-15〜)

詳細: `references/v3-core.md`
プロジェクト固有値の適用例: `references/profiles/build-factory.md`

> **注意**: 以下の v3 ルールは「プロジェクト依存値」を含む。固定の数値・script path は規定しない。固有値は profile 経由で注入する (profile は **例** であり必須ではない)。

1. **上流出力を必ず pull** — task-decomposition の tickets.json (3-tier AC) と api-design の ears-ac-seed.json (EARS AC) を STEP 1 で path 確認
2. **3-tier AC を test レベルに 1:1 マッピング** — structural → mock/spec drift lint / functional → unit + contract + access-control / regression → CI gate 自動化
3. **EARS AC から test case 自動生成** — EVENT-DRIVEN → 正常系 / UNWANTED → 異常系 / STATE-DRIVEN → parametrize。`<ears_test_generator>` script 経由
4. **Access control matrix test (role × operation)** — 必須網羅。role 数・operation 数・期待値 (OK/NG) は project-defined。`<access_control_verifier>` で CI 検証
5. **N CI gate を Foundation → Backend → UI → Polish の段階で構成** — gate 数 N は project-defined (e.g., 5-10)。各段階の代表 gate:
   - Foundation gate: lint / format / AC validator / type check
   - Backend gate: access-control coverage / API contract test / coverage threshold (project-defined, e.g., 70-90%)
   - UI gate: tsc / mock-impl drift / visual regression
   - Polish gate: audit MD existence / perf / security scan
6. **auto-merge** — 全 gate pass で auto-merge、連続 N 失敗で human エスカ
7. **Contract test 必須** — Schemathesis (OpenAPI → fuzz) + Pact (frontend ↔ backend consumer/provider)。openapi.yaml を api-design から pull

---

## テンプレートファイル（assets/）
- `assets/jest-config-template.ts` — jest.config.tsテンプレート（カバレッジ閾値・パスエイリアス設定済み）
- `assets/ci-template.yml` — CI テンプレート（Lint・型チェック・テスト・ビルドの基本ジョブ構成）

STEP 3（カバレッジ基準・CI設計）の最終出力時は、jest-config-template.tsのcoverageThresholdsとci-template.ymlをプロジェクトに合わせて調整した形で出力すること。

---

## STEP 1: テスト対象とリスク評価 (v3: 3-tier AC マッピング + 上流出力 pull)

**このSTEPでやること：**
何をテストするか・何をテストしないかを決める。全部テストするのは現実的ではないので、リスクと価値のバランスで優先順位をつける。

**v3 必須**: 上流出力の path を確認し、3-tier AC を test レベルに 1:1 マッピング:

```
## 入力情報の確認 (v3)

### 上流出力
- task-decomposition 出力: docs/task-decomposition/<date>_v<N>/
  - tickets.json: N 件 (3-tier AC 込み)
- api-design 出力: docs/api-design/<date>_v<N>/
  - openapi.yaml (Schemathesis input)
  - ears-ac-seed.json (EARS AC ドラフト)
  - lint-mapping.json (mock ↔ API 対応の lint 検証対象)
- functional-breakdown 出力: docs/functional-breakdown/<date>_v<N>/
  - entities.json (access control policy)
  - roles.json (project-defined roles, e.g., 3-10 roles)
- architecture-design 出力: docs/architecture/<date>_v<N>/
  - foundation_gates.json (CI gate 定義 / N gates project-defined)

### 3-tier AC ↔ test レベル マッピング (v3 必須)
| 3-tier AC | test レベル | tool | gate 段階 |
|---|---|---|---|
| structural (mock/spec 一致) | mock-impl drift lint | <mock_impl_diff> | UI gate |
| functional.api (EARS) | unit + contract | pytest/vitest + Schemathesis | Backend gate |
| functional.access_control (role × operation matrix) | access-control test | <access_control_verifier> | Backend gate |
| functional.acceptance | E2E | Playwright/Cypress | UI gate |
| regression.coverage | coverage check | coverage tool (project-defined threshold) | Backend gate |
| regression.lint | mock-lint + AC validator | <lint_runner> + <ac_validator> | Foundation gate |
| regression.type | type check | pyright/tsc/mypy | Foundation gate |
| regression.audit | audit MD existence | <audit_md_check> | Polish gate |
```

**確認すること（曖昧なら【仮説】を立てて質問）：**

1. **実装内容** — どの機能・APIを対象とするか？複数ある場合はリスト
2. **技術スタック** — テストフレームワークは決まっているか？(Jest / Vitest / pytest など)
3. **既存のテスト状況** — テストは既にあるか？あるならどのレベルまでカバーされているか？
4. **リスクの高い箇所** — 「ここが壊れると一番困る」機能はどこか？(認証・決済・データ処理など)
5. **テストに使える時間・リソース** — 全部丁寧にやる余裕があるか、最小限でよいか？
6. **CIの有無** — CI 環境はあるか？ (GitHub Actions / GitLab CI / CircleCI など)
7. **v3: tickets.json の 3-tier AC schema 適合** — 全 task が structural / functional / regression に分かれているか
8. **v3: ears-ac-seed.json の EARS 形式** — EVENT-DRIVEN + UNWANTED 1 件以上を全 endpoint で確認
9. **v3: N CI gate 採用方針** — gate 数 / 各段階の構成 (Foundation/Backend/UI/Polish) / 一部 skip 判断 (例: 序盤で access-control gate をまだ ON にしない等)
10. **v3: contract test (Schemathesis + Pact) 採用方針** — frontend/backend の契約検証を CI に含めるか
11. **v3: access control role × operation matrix** — role 数・operation 数・期待値 (OK/NG) の確定 (project-defined; profile 参照可)

**出力形式：**

```
## テスト対象・リスク評価

### テスト対象機能
[機能名と概要のリスト]

### リスク評価
| 機能 | リスク | 理由 | テスト優先度 |
|-----|-------|------|------------|
| 認証 | 高 | セキュリティ直結 | 最優先 |
| 一覧取得 | 中 | データ整合性 | 優先 |
| UI表示 | 低 | 視覚的確認で十分 | 後回し |

### テストしないもの（理由とともに）
- [機能名]：理由（例：手動確認で十分 / スコープ外 / 変更頻度が高い）

### テストフレームワーク確認
- 既定 or 【仮説】：
- 既存テスト：（あり / なし / 部分的）
```

---

📦 **STEP 1 確認**

テスト対象・リスク評価を確認してください。

- リスク評価の優先度は実際の感覚と合っていますか？
- テストしないものの判断は適切ですか？
- 問題なければ「STEP 2へ」とお知らせください

**※ STEP 2には進まない。ユーザーの確認を待つ。**

---

## STEP 2: テスト種類と粒度の設計 (v3: EARS 自動生成 + access-control matrix)

**このSTEPでやること：**
unit / integration / E2E / contract / access-control のどのレベルでテストするかを機能ごとに決める。

**v3 必須**:
- **EARS AC → test case 自動生成** (`<ears_test_generator>` script)
  - EVENT-DRIVEN → `test_<endpoint>_<event>()` (正常系)
  - UNWANTED → `test_<endpoint>_<condition>_rejected()` (異常系)
  - STATE-DRIVEN → `parametrize("state", [...])` で分岐
- **Access control test は role × operation matrix で網羅必須**
  - role 数: project-defined (e.g., 3-10 roles)
  - operation 数: project-defined (e.g., 5-8 operations: SELECT own / SELECT others / INSERT / UPDATE own / UPDATE others / DELETE own / DELETE others 等)
  - entity 1 件あたりの test case 数 = role 数 × operation 数
  - `<access_control_verifier>` で網羅検証
- **Contract test**: Schemathesis (OpenAPI → fuzz) + Pact (frontend ↔ backend consumer/provider)

**Webリサーチ（STEP 2で実施）：**
採用テストフレームワークのベストプラクティスを調査する：
- 使用フレームワーク（Jest/Vitest/pytest等）の最新の推奨設定・プラグイン
- 同業界・同技術スタックでのテストカバレッジ基準事例
- E2Eテストツール（Playwright/Cypress）の選定比較（E2Eが必要な場合）

調査結果はデータ蓄積JSONの `research` フィールドに保存。

**テストピラミッドの考え方：**
- **ユニットテスト**（多く・速く・安い）: 関数・メソッド単位の動作検証
- **統合テスト**（中程度）: APIエンドポイント・DB操作の組み合わせ検証
- **E2Eテスト**（少なく・遅く・高い）: ユーザーの実際の操作フロー検証

受託開発の現実解：E2Eは最小限にして、APIレベルの統合テストをメインにする。

**出力形式 (v3)：**

```
## テスト設計 (v3)

### テストレベル配分
| 機能 | unit | contract | access-control | E2E | EARS 自動生成 | 理由 |
|-----|------|----------|----------------|-----|--------------|------|

### EARS 自動生成 test (v3)
- 入力: docs/api-design/<date>_v3/ears-ac-seed.json
- 出力: <test_dir>/generated/
- script: <ears_test_generator>
- 命名規則:
  - EVENT-DRIVEN → test_<endpoint>_<event>()
  - UNWANTED → test_<endpoint>_<condition>_rejected()
  - STATE-DRIVEN → parametrize 経由

### Access control test (v3 / role × operation matrix)
※ role / operation / 期待値は project-defined。下表は構造例 (実値は profile 参照)。

| role        | op_1 (SELECT own) | op_2 (SELECT others) | op_3 (INSERT) | op_4 (UPDATE own) | ... |
|-------------|-------------------|----------------------|---------------|-------------------|-----|
| <role_a>    | OK                | OK                   | OK            | OK                | ... |
| <role_b>    | OK                | OK                   | OK            | OK                | ... |
| <role_c>    | OK                | NG                   | OK            | OK                | ... |
| <role_d>    | OK (assigned)     | NG                   | NG            | NG                | ... |

- entity 1 件あたり = (role 数) × (operation 数) test case
- 検証: <access_control_verifier>
- Backend gate で CI 自動検証

### Contract test (v3)
- Schemathesis: OpenAPI → fuzz (property-based test)
- Pact: frontend (consumer) ↔ backend (provider) 契約検証
- 入力: docs/api-design/<date>_v3/openapi.yaml

### E2Eテスト設計（最小限 / Playwright or Cypress）
- クリティカルなユーザーフローのみ

### モック戦略
- DBはモックするか・しないか（理由）
- 外部APIはスタブするか（理由）
```

---

📦 **STEP 2 確認**

テスト設計を確認してください。

- テストレベルの配分は現実的ですか？
- モック戦略は実際のプロジェクトに合っていますか？
- 問題なければ「STEP 3へ」とお知らせください

**※ STEP 3には進まない。ユーザーの確認を待つ。**

---

## STEP 3: カバレッジ基準・CI設計・受け入れ基準 (v3: N CI gate auto-merge / 段階構成)

**このSTEPでやること：**
テストが「通った」とはどういう状態かを定義する。**v3: N CI gate (project-defined, e.g., 5-10) を Foundation → Backend → UI → Polish の段階で構成し、auto-merge を必須化**。

**カバレッジ基準の現実解：**
- ビジネスロジック・認証・データ操作: 80%以上
- ユーティリティ・型変換: 60%以上
- **v3 統一基準: 全体 coverage ≥ project-defined threshold (e.g., 70-90%)** — Backend gate で検証

**出力形式 (v3)：**

```
## カバレッジ基準・受け入れ基準 (v3)

### N CI gate (v3 必須 / Foundation → Backend → UI → Polish 段階構成)
※ N と各 gate の具体名/script path は project-defined。下表は段階構成の例。

| 段階 | Gate 名 | tool | 失敗条件 |
|---|---|---|---|
| Foundation | lint / format | <lint_runner> | lint rule violation |
| Foundation | AC validator | <ac_validator> | 3-tier AC schema 違反 or EARS 形式違反 |
| Foundation | type check | pyright / tsc / mypy | type error |
| Backend | access-control coverage | <access_control_verifier> | role × operation matrix 未網羅 |
| Backend | API contract | Schemathesis (+ Pact verify) | contract violation |
| Backend | coverage threshold | coverage tool | カバレッジ < project-defined threshold or test failure |
| UI | tsc strict | tsc --noEmit | type error |
| UI | mock-impl drift | <mock_impl_diff> | mock の項目が backend response に存在しない |
| UI | visual regression (任意) | Playwright/Chromatic | snapshot diff |
| Polish | audit MD existence | <audit_md_check> | 該当 task の audit MD が存在しない |
| Polish | perf budget (任意) | Lighthouse / k6 | budget violation |
| Polish | security scan (任意) | npm audit / pip-audit / Snyk | high/critical vuln |

### 段階間の block 関係 (v3)
- Foundation gate 不合格 → Backend / UI / Polish 全 skip
- Backend gate 不合格 → UI / Polish 全 skip
- UI gate 不合格 → Polish 全 skip
- 全段階 pass → auto-merge

### auto-merge (v3 必須)
- needs: [全 gate] 全 pass
- 動作: `gh pr merge --auto --squash`
- 連続 N 失敗 (project-defined, e.g., 3) で human エスカ (Slack / メール)
- 例外: 一部 gate を初期段階で OFF にする場合は foundation_gates.json の override で明示

### カバレッジ基準
| 対象 | 最低カバレッジ | 重点テスト対象 |
|-----|-------------|------------|
| ビジネスロジック / 認証 / データ操作 | 80% | access-control / 認証 / 決済 |
| ユーティリティ / 型変換 | 60% | - |
| v3 統一: 全体 | project-defined (e.g., 70-90%) | Backend gate |

### マージ可能の判断基準 (v3 / Done → auto-merge)
- [ ] N CI gate 全て green
- [ ] EARS AC → test case 自動生成済 (ears-test-mapping.json で対応取れている)
- [ ] Access control role × operation matrix 網羅 (<access_control_verifier> pass)
- [ ] Schemathesis contract test pass (任意)
- [ ] Pact contract verify pass (任意)
- [ ] 連続 N 失敗していない (もしくは human escalate 完了)

### リグレッション防止 (v3)
- 全 EARS AC が ears-test-mapping.json に登録 → 仕様変更時に test の追従漏れを CI で検出
- mock-impl drift lint (UI gate) で mock ↔ 実装 drift を毎 PR 検出
- 並列開発期間中の drift fix 専用 group を継続稼働
```

---

📦 **STEP 3 確認**

受け入れ基準を確認してください。

- カバレッジ基準は現実的ですか（高すぎず低すぎず）？
- 「マージ可能」の判断基準に漏れはありますか？
- 問題なければ「STEP 4へ」とお知らせください

**※ STEP 4には進まない。ユーザーの確認を待つ。**

---

## STEP 4: 最終出力 (v3: 4 形式同時出力)

### 出力① テスト計画書 (Markdown)

```markdown
# テスト計画書

## 対象機能とリスク評価
## 3-tier AC ↔ test レベル マッピング (v3)
## テスト設計 (unit / contract / access-control / E2E)
## EARS AC 自動生成方針 (v3)
## Access control role × operation matrix (v3)
## N CI gate 段階構成 (Foundation/Backend/UI/Polish, v3)
## カバレッジ基準
## マージ可能判断基準 (auto-merge)
```

### 出力② テスト設計 JSON

```json
{
  "version": "v3",
  "project_id": "",
  "test_strategy": {
    "framework": "<framework_set>",
    "coverage_thresholds": {
      "business_logic": 80,
      "utilities": 60,
      "overall": "<project-defined, e.g., 70-90>"
    },
    "ci_gates": {
      "foundation": ["lint", "format", "ac-validator", "type-check"],
      "backend": ["access-control-coverage", "contract-test", "coverage-threshold"],
      "ui": ["tsc-strict", "mock-impl-diff"],
      "polish": ["audit-md-existence"]
    },
    "merge_criteria": ["all gates green", "ears-test-mapping consistent", "access-control matrix complete"]
  },
  "test_cases": [],
  "next_skill": "distributed-dev"
}
```

### 出力③ gate-config.yml (v3 新規 / CI runner 設定)

> 下記は段階構成の例。gate 数 / script path / runner 詳細は project-defined。

```yaml
name: N CI Gate (Foundation -> Backend -> UI -> Polish)
on: [pull_request]

jobs:
  # ----- Foundation gate -----
  foundation-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash <lint_runner>

  foundation-ac-validator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 <ac_validator>

  foundation-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pyright   # or tsc / mypy

  # ----- Backend gate (depends on Foundation) -----
  backend-access-control-coverage:
    needs: [foundation-lint, foundation-ac-validator, foundation-type-check]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 <access_control_verifier>

  backend-contract-test:
    needs: [foundation-lint, foundation-ac-validator, foundation-type-check]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: schemathesis run docs/api-design/openapi.yaml --base-url http://localhost:8000

  backend-coverage:
    needs: [foundation-lint, foundation-ac-validator, foundation-type-check]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest --cov --cov-fail-under=<project-defined-threshold>

  # ----- UI gate (depends on Backend) -----
  ui-tsc:
    needs: [backend-access-control-coverage, backend-contract-test, backend-coverage]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: tsc --noEmit

  ui-mock-impl-diff:
    needs: [backend-access-control-coverage, backend-contract-test, backend-coverage]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 <mock_impl_diff>

  # ----- Polish gate (depends on UI) -----
  polish-audit-md:
    needs: [ui-tsc, ui-mock-impl-diff]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash <audit_md_check>

  # ----- auto-merge -----
  auto-merge:
    needs: [polish-audit-md]
    runs-on: ubuntu-latest
    steps:
      - name: Auto-merge PR
        run: gh pr merge --auto --squash
```

### 出力④ ears-test-mapping.json (v3 新規)

```json
{
  "version": "v3",
  "skill": "test-verification",
  "mappings": [
    {
      "ears_ac_id": "F-001-AC-01",
      "ears_form": "EVENT-DRIVEN",
      "ears_text": "When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.",
      "test_id": "TC-001",
      "test_file": "<test_dir>/generated/test_auth_login.py",
      "test_function": "test_auth_login_valid_credentials",
      "test_level": "unit+contract",
      "gate": "backend-coverage"
    },
    {
      "ears_ac_id": "F-001-AC-02",
      "ears_form": "UNWANTED",
      "ears_text": "If credentials are invalid, the system shall return 401 with generic message (no user enumeration).",
      "test_id": "TC-002",
      "test_file": "<test_dir>/generated/test_auth_login.py",
      "test_function": "test_auth_login_invalid_credentials_rejected",
      "test_level": "unit+contract",
      "gate": "backend-coverage"
    }
  ]
}
```

---

## 📦 構造化JSON出力仕様（最終ステップのみ）

```devos-json
{
  "strategy": {"approach": "TDD + E2E", "coverage_target": 80, "tools": ["Jest", "Playwright"]},
  "test_cases": [
    {
      "id": "TC-001",
      "title": "テストケース名",
      "category": "unit",
      "priority": "high",
      "status": "pending",
      "steps": ["ステップ1", "ステップ2"],
      "expected_result": "期待される結果"
    }
  ],
  "ci_config": "CI設定の概要",
  "coverage_report": {"unit": 0, "integration": 0, "e2e": 0}
}
```
