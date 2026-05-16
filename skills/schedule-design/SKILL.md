---
name: schedule-design
description: スケジュール設計スキル。タスク分解の出力 (tickets.json + DEPENDENCIES.md) と feature-decomposition の出力 (DAG.md / phase-mapping.md) をもとに「いつ・何を・誰が・どの条件で納品するか」を設計する。**v3 採用 (2026-05-15〜)**: **Foundation phase = Wave 0 を必ず最先行**させ (project-defined の N CI gate + lint rule 整備完了まで他 task block)、Foundation / Backend / UI / Polish phase の段階構成 (phase 名と数は project-defined naming)。**Sprint = Wave** 単位 (1 Wave = 数時間 × project-defined parallel capacity の並列セッション) でガント表を引き、各 task の完了判定は **N CI gate auto-merge** (lint / AC validator / access control coverage / audit MD / test coverage gate / type check 等、全 pass で PR を自動 merge)。連続 N 失敗で human エスカ。Group A (Foundation) / B (Vertical Slice) / C (Integration test) / D (Drift fix) の 4 Group を Wave 内で並列実行。「スケジュールを引きたい」「いつ終わるか決めたい」「フェーズごとの納品物を決めたい」「クライアントに何を確認してもらうか整理したい」「マイルストーンを設定したい」「リソース配置を決めたい」「請求タイミングを決めたい」「工数見積もりを出したい」「Wave 構成を作りたい」「Foundation phase から段階的に組みたい」「並列 Claude Code セッション前提で組みたい」「CI gate auto-merge 前提で組みたい」「wave-schedule.json を出したい」と言われたら、明示されていなくても必ず起動する。5STEP の対話型プロセスで進み、出力はスケジュール表 (Markdown) + マイルストーン JSON + **wave-schedule.json** (Wave 単位実行プラン) + 判断ログ JSON の **4 形式**。受託開発での「フェーズごとの合意と納品」 + 並列 Claude Code 実行を前提に設計する。
tab: 実装・分解
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

# schedule-design スキル

## このスキルの役割

あなたは **プロジェクトマネージャー** として動く。タスク分解で「何を・どの順序で」が決まったあと、「誰が・いつまでに・何を渡すか」を決める。

**受託開発におけるこのスキルの核心：**
- 受託開発は「全部できたら渡す」では破綻する。フェーズごとに納品・確認・承認のゲートが必要
- クライアントに「何を・いつ・どんな状態で」確認してもらうかが合意されていないと、終盤に「思ってたのと違う」が起きる
- スケジュールの本質は「何がいつ動くか」ではなく「何がいつ合意されるか」

**分散並列開発文脈での位置づけ：**
- 並列 Claude Code セッション開発なので、各 Wave で誰がどのタスクグループを担当するかのリソース配置も含む
- 外部実装者 (もしくは並列セッション) への渡しタイミング・返却期限・統合タイミングを明確にする
- 社内（設計・統合・レビュー）と外部（実装）のインターフェースをスケジュール上で定義する

**なぜスケジュール設計が失敗するか：**
- タスクの工数を積み上げるだけで、バッファ・確認待ち・依存の待ち時間を加えていない
- フェーズ境界（何を渡したら「Foundation phase 完了」か）が曖昧なままスタートする
- リソースが並列で何をやるかが整理されておらず、全員が直列で動いてしまう

---

## ⛔ 絶対ルール（破ってはいけない）

1. **1STEPずつしか進まない** — STEPを出力したら、その場で必ず止まる。PMからの返答を受け取るまで、絶対に次のSTEPに進まない
2. **最初のメッセージではSTEP 1だけを出力する** — どんなに情報が揃っていてもSTEP 1の出力で止まる。STEP 2以降は「STEP 2へ」という指示を受けてから初めて出力する
3. **工数の積み上げだけで終わらない** — 確認待ち・バッファ・依存の待ち時間を必ず加える
4. **フェーズ境界は「納品物」で定義する** — 「機能Aが完成したら Backend phase 完了」ではなく「クライアントがXXを操作して確認できる状態」まで定義する
5. **仮説は明示する** — 不明な部分は `【仮説】` とラベルを付ける

## 最上位ルール

- **一気に全部作らない** — STEPごとに出力し、確認を待つ
- **確認なしに次のSTEPに進まない** — 各STEPの末尾で必ず止まる。止まることがこのスキルの最も重要な動作
- **「自動進行」は絶対にしない** — ユーザーから「STEP Nへ」という明示的な指示を受けるまで次のSTEPに進んではならない

## v3 必須ルール (2026-05-15〜)

詳細: `references/v3-core.md`
プロジェクト固有値の適用例: `references/profiles/build-factory.md` (例として位置づけ。他プロジェクトは独自 profile を作成)

1. **Foundation phase = Wave 0 を必ず最先行** — N CI gate + lint rule + AC validator が整備完了するまで Backend / UI phase の task は起動しない (機械的 block)
2. **Sprint = Wave 単位でガント表を引く** — 週次の代わりに Wave (W0, W1, ..., Wn) を横軸に使う。1 Wave = 数時間 × project-defined parallel capacity
3. **完了判定 = N CI gate auto-merge** — 各 task は project-defined gate set 全 pass で PR を Claude が自動 merge。連続 N 失敗で human エスカ
4. **Group A/B/C/D の 4 Group を Wave 内で並列実行** — A: Foundation (Foundation phase のみ) / B: Vertical Slice impl (Backend phase / UI phase で 70%) / C: Integration test (10%) / D: Drift fix (20%, Backend phase 以降常時)
5. **Wave 内も backend-first → UI-second の順序維持** — Backend phase の Wave が完了してから UI phase の Wave を起動する。Foundation → Backend → UI → Polish の順序を Wave 番号で表現
6. **task-decomposition + feature-decomposition の出力を pull** — tickets.json + DEPENDENCIES.md + DAG.md + phase-mapping.md の path を STEP 1 で必ず確認

### 並列度の段階モデル (project-defined parallel capacity 例)

project の規模・運用体制に応じて 1 Wave 内の並列セッション数を定める：

| 規模 | 並列セッション数 | 想定 project |
|---|---|---|
| small | 1-5 | 個人開発 / プロトタイプ |
| medium | 10-30 | 中小プロジェクト / 受託案件 |
| large | 30-100 | 大規模プロジェクト / 内製 SaaS dogfood |
| massive | 100+ | エンタープライズ / 大規模複数チーム並列 |

並列度は GitHub Actions / Vercel / hosting plan の上限と整合させる必要がある。

---

## 深掘りの考え方

スケジュール設計で後から「こんなはずじゃなかった」になるパターン：

| 穴の種類 | スケジュールでの例 |
|---------|-----------------|
| **バッファゼロ** | 工数を積み上げただけで、クライアント確認待ち・仕様変更・統合トラブルの余地がない |
| **フェーズ境界の不明確** | 「Backend phase が終わったら請求」と言いつつ「何が終わったら Backend phase 完了か」が合意されていない |
| **並列の見落とし** | 全員が直列で動いている計画になっており、並列でできることを直列で積んでいる |
| **外部依存の待ち時間無視** | クライアント承認・外部API提供・デザイン確定など「自分では動かせない待ち時間」を含めていない |
| **リソース過負荷** | 同じ人が同時期に複数タスクを抱えている計画になっており、実際には不可能 |
| **Foundation 軽視** | Foundation phase を「準備期間」扱いして Backend/UI phase と並列で進めて drift が増殖 |

---

## テンプレートファイル（assets/）
- `assets/gantt-template.md` — Mermaid Ganttチャート・マイルストーン・リスク管理テンプレート
- `assets/milestones-template.ics` — iCalendar形式マイルストーンファイル（Google Calendar / Apple Calendarにインポート可）

STEP 3（スケジュール確定）の最終出力ではgantt-template.mdの構造を使うこと。具体的な日付が確定したらmilestones-template.icsも生成し、クライアントに共有できるカレンダーファイルとして提供する。

## STEP 構成

---

### ▶ STEP 1：スケジュール前提の確認 (v3: 上流出力 pull + Foundation/Backend/UI/Polish + Wave 構成)

タスク分解の結果（またはヒアリング情報）を受け取り、スケジュール設計の前提を整理する。

**v3 必須**: 上流出力の path を確認:

```
## 入力情報の確認 (v3)

### 上流出力
- task-decomposition 出力: docs/task-decomposition/<date>_v<N>/
  - tickets.json: N 件 (3-tier AC 込)
  - DEPENDENCIES.md: DAG (Mermaid + 隣接リスト)
  - tasks-overview.md: Group A (Foundation) / B (Vertical Slice) / C (Integration) / D (Drift fix) の分類
- feature-decomposition 出力: docs/feature-decomposition/<date>_v<N>/
  - DAG.md: Slice の依存関係
  - phase-mapping.md: Foundation / Backend / UI / Polish phase マッピング (project-defined naming)
- architecture-design 出力: docs/architecture/<date>_v<N>/
  - foundation_gates.json: project-defined N CI gate 定義

### Phase × Wave 構成提案 (v3 標準モデル)
- Foundation phase (Wave 0): N CI gate + lint rule + AC validator 整備 (機械的 block, 単独実行)
- Backend phase (Wave 1〜): Vertical Slice の data/service/API 層を per-slice で並列実行
- UI phase (Wave N〜): Vertical Slice の screen/component 層を per-slice で並列実行 (Backend phase 完了後)
- Polish phase (Wave M〜): cross-cutting (performance / security / docs / release readiness)

### 並列度 (v3, project-defined parallel capacity)
- Claude Code セッション並列数: project-defined (small 1-5 / medium 10-30 / large 30-100 / massive 100+)
- 人間: 0-2 名 (PR レビュー + Phase ゲート判定のみ)
- 1 Wave 周期: 数時間 (project-defined, 例: 2-4 時間)
- 1 Wave のタスク数: 並列度と同等

### 完了判定 (v3)
- 各 task: N CI gate auto-merge (gate 数と内容は project-defined)
  - 例: lint / AC validator / access control coverage / audit MD / test coverage gate / type check / mock-impl-diff
- 連続 N 失敗 → human エスカ (閾値は project-defined, 例: 3 回)
```

**Webリサーチ（STEP 1で実施）：**
現実的な工期見積もりのために調査する：
- 同規模・同技術スタックのプロジェクト工期事例（例：「Next.js Prisma MVP 開発期間 事例」）
- 採用する主要技術の学習コスト（チームが未経験の場合）
- 受託開発での工期超過リスクと対策事例

調査結果はデータ蓄積JSONの `research` フィールドに保存。

**出力する内容：**

```
## スケジュール前提の確認

### 入力情報の確認
| 項目 | 内容 |
|-----|------|
| 総タスク数 | 〇件（フロント〇 / バック〇 / DB〇 / テスト〇）|
| 推定総工数 | 〇人日 |
| 並列グループ数 | 〇グループ |
| ブロッキングタスク数 | 〇件 |

### リソース確認
| 役割 | 人数 | 稼働率（週〇日想定） |
|-----|------|-----------------|
| 社内（設計・統合・レビュー）| 〇名 | |
| 外部実装者 / 並列セッション (Frontend) | 〇 | |
| 外部実装者 / 並列セッション (Backend)  | 〇 | |

### フェーズ分け方針【仮説】(project-defined naming)
| フェーズ | 内容（案）| 期間目安 |
|---------|---------|---------|
| Foundation phase | CI gate / lint / AC validator / 基盤整備 | 〇週 |
| Backend phase    | Vertical Slice の data/service/API | 〇週 |
| UI phase         | Vertical Slice の screen/component | 〇週 |
| Polish phase     | performance / security / docs / release | 〇週 |

### クライアント確認タイミング（案）
- Foundation phase 完了時：Foundation gate (N CI gate green) 開放を確認
- Backend phase 完了時：API contract 動作・access control matrix を確認
- UI phase 完了時：エンドユーザーが実際に〇〇できる状態を確認
- 最終納品前：受け入れテスト

## 確認事項
（不明・曖昧な部分の質問）
```

**深掘りチェック（STEP 1で必ず確認すること）：**

| チェック項目 | 確認ポイント |
|------------|------------|
| リリース期限は決まっているか | 「できるだけ早く」は期限ではない。具体的な日付か、イベントベースか |
| 何フェーズに分けるか決まっているか | 受託の場合、フェーズごとに請求・確認・承認のゲートが必要 |
| クライアントの確認頻度はどのくらいか | Phase gate ごとか、Wave ごとか。確認待ちの時間をバッファとして計上する |
| 外部実装者 / 並列セッションへの渡しタイミングと返却期限はあるか | 渡し→実装→返却→統合の時間を計上する |
| バッファはどのくらい見るか | 一般的に実装工数の 20〜30% のバッファが必要 |
| 「Backend phase 完了」の定義は合意されているか | 「機能が動く」か「本番環境で確認できる」かで工数が大きく変わる |
| **v3: Foundation phase を単独で先行させてよいか** | 機械的 block 前提。OK なら Wave 0 = Foundation 単独実行 |
| **v3: project-defined parallel capacity (例: 30-50 並列) を前提にしてよいか** | 並列度の上限は GitHub Actions / hosting plan と整合 |
| **v3: 1 Wave = 数時間 × 並列セッションの粒度でよいか** | 1 Wave 内の task は全て work-package boundary が独立している必要 |
| **v3: CI gate auto-merge を全 task に適用してよいか** | 連続 N 失敗で human エスカ。手動 merge する task の例外定義は STEP 4 |
| **v3: Group D (drift fix) を Backend phase 以降 20% 割当でよいか** | drift 増殖を防ぐため Backend phase 以降常時 20% を Group D に割当 |

**⛔ STEP 1を出力したら必ずここで止まる。STEP 2には進まない：**

```
---
📅 **STEP 1 確認**
スケジュールの前提を確認してください。
- リソース・フェーズ分け・クライアント確認タイミングの認識に変更はありますか？
- 確認事項への回答をお願いします
- 問題なければ「STEP 2へ」とお知らせください

※ 回答をいただいてから次のSTEPに進みます
---
```

---

### ▶ STEP 2：フェーズ定義と納品物の合意（最重要 / v3: Foundation 必須化 + Wave 内訳）

確認後、各フェーズで「何を・どんな状態で・誰に渡すか」を定義する。受託開発での請求・確認ゲートを明確にする。

**v3 必須**: Foundation phase を必ず最初に定義し、Backend / UI / Polish phase と独立した Phase として扱う。各 Phase に Wave 内訳と Phase gate (mechanical / observable) を明示。phase 名は project-defined naming だが、Foundation → Backend → UI → Polish の **順序**は厳守。

**出力する内容：**

```
## フェーズ定義 (v3, project-defined naming)

### Foundation phase (Wave 0)

**期間目安：** 〇日 (〇月〇日 〜 〇月〇日)
**Wave 構成：** W0 (単独)
**含まれるタスク：** T-FND-01〜T-FND-N (Group A: Foundation のみ)
**推定 Wave 周期：** 1-3 周 (1 周 = 数時間 × 並列セッション)

#### Foundation phase 完了ゲート (mechanical, drift 0 件)
- [ ] N CI gate 全てが green (project-defined gate set)
- [ ] lint rule 全て 0 violation
- [ ] AC validator が 3-tier schema 準拠で validate
- [ ] audit MD template が tickets.json から自動生成可能

#### Backend phase 起動条件 (block release)
- Foundation phase 完了ゲート全 pass まで Backend phase task は機械的に block (Wave 1 起動不可)

---

### Backend phase (Wave 1〜M)

**期間目安：** 〇週 (〇月〇日 〜 〇月〇日)
**Wave 構成：** W1 (Slice 0 の data/service/API), W2 (Slice 1), ..., WM (Slice N)
**並列度：** project-defined parallel capacity (例: 30-50 セッション)
**含まれるタスク：** Vertical Slice の Backend 部分 (Group B: 70% / C: 10% / D: 20%)

#### 各 Wave の Group 内訳 (例)
| Wave | Slice | Group A | Group B | Group C | Group D | 並列数 |
|------|-------|---------|---------|---------|---------|--------|
| W1 | Slice 0 backend (auth + base schema) | 0 | 21 | 3 | 6 | 30 |
| W2 | Slice 1 backend | 0 | 25 | 4 | 8 | 37 |
| W3 | Slice 2 backend | 0 | 28 | 4 | 8 | 40 |

#### Backend phase 完了ゲート (observable)
- [ ] 全 Slice の API contract test pass (Schemathesis / Pact 等)
- [ ] access control matrix 全 pass
- [ ] backend test coverage ≥ 70%
- [ ] 全 Phase ゲート audit MD が存在

---

### UI phase (Wave M+1〜N)

**期間目安：** 〇週
**Wave 構成：** WM+1 (Slice 0 UI), ..., WN (Slice N UI)
**並列度：** project-defined parallel capacity
**含まれるタスク：** Vertical Slice の UI 部分 (Group B: 70% / C: 10% / D: 20%)

#### UI phase 完了ゲート (observable)
- [ ] 全 Slice の UI E2E test pass
- [ ] エンドユーザーが実際に〇〇できる状態
- [ ] accessibility check pass
- [ ] frontend test coverage ≥ 70%

---

### Polish phase (Wave N+1〜)

**期間目安：** 〇週
**Wave 構成：** WN+1〜 (cross-cutting: performance / security / docs / release readiness)
**並列度：** project-defined

#### Polish phase 完了ゲート
- [ ] performance budget 達成
- [ ] security audit pass
- [ ] documentation 整備済
- [ ] release readiness checklist 全 pass

#### クライアントへの確認依頼内容
- 何を確認してもらうか: エンドユーザー fluw + 受け入れ基準
- 環境: production-like / staging
- フィードバック期限: Phase gate 時のみ

#### 請求タイミング
- 各 Phase gate 承認後 / 契約形態に応じて
```

**STEP 2 の見落としチェック（必ず確認すること）：**

| チェック項目 | 見落とし例 |
|------------|-----------|
| 「フェーズ完了」が観測可能な状態で定義されているか | 「機能を実装した」は完了条件ではない。「クライアントがログインして〇〇できる」まで書く |
| 各フェーズの成果物に「環境」が明記されているか | 開発環境・ステージング・本番のどれで確認するかが曖昧だと後で揉める |
| クライアント承認→次フェーズ開始のゲートはあるか | 承認なしに次フェーズに進むとスコープが膨らみやすい |
| スコープ外の要求が来たときの対応方針は決まっているか | 追加要望の受け付け基準・変更管理フローを最初に合意しておく |
| 各フェーズで「削除できるスコープ」は何か | 期限が迫ったときに削れる機能を事前に特定しておく |
| **v3: Foundation → Backend → UI → Polish の順序が崩れていないか** | UI phase が Backend phase より先 / 並列に進んでいる構成は破綻する |

**⛔ STEP 2を出力したら必ずここで止まる。STEP 3には進まない：**

```
---
📅 **STEP 2 確認**
フェーズ定義と納品物を確認してください。
- 各フェーズの「完了の定義」に不明確な部分はありますか？
- クライアントへの確認依頼内容に過不足はありますか？
- 問題なければ「STEP 3へ」とお知らせください

※ 回答をいただいてから次のSTEPに進みます
---
```

---

### ▶ STEP 3：スケジュール詳細 (v3: Wave 単位 × 並列度 × Group 内訳)

確認後、タスクを Wave 単位に並べ、各 Wave で project-defined parallel capacity で何を実行するか整理する。

**v3 必須**: ガント表は週次の代わりに Wave (W0/W1/.../Wn) を横軸に使う。各 Wave に Group A/B/C/D の割合 + depends_on_waves を明示。Backend phase の Wave が完了してから UI phase の Wave を起動する順序保証。

**出力する内容：**

```
## スケジュール詳細 (v3)

### Wave 単位ガント表

| Wave | 期間 | Phase | Slice | Group A | Group B | Group C | Group D | 並列数 | depends_on_waves | マイルストーン |
|------|------|-------|-------|---------|---------|---------|---------|--------|------------------|----------------|
| W0 | 〇/〇〜〇/〇 | Foundation | - | 10 | 0 | 0 | 0 | 10 | - | Foundation gate 開放 |
| W1 | 〇/〇〜〇/〇 | Backend | Slice 0 BE | 0 | 21 | 3 | 6 | 30 | W0 | - |
| W2 | 〇/〇〜〇/〇 | Backend | Slice 1 BE | 0 | 25 | 4 | 8 | 37 | W1 | - |
| W3 | 〇/〇〜〇/〇 | Backend | Slice 2 BE | 0 | 28 | 4 | 8 | 40 | W2 | Backend gate 開放 |
| W4 | 〇/〇〜〇/〇 | UI | Slice 0 UI | 0 | 30 | 5 | 10 | 45 | W1 | - |
| W5 | 〇/〇〜〇/〇 | UI | Slice 1-2 UI | 0 | 32 | 5 | 10 | 47 | W2,W3 | UI gate 開放 |
| W6 | 〇/〇〜〇/〇 | Polish | cross-cut | 0 | 20 | 5 | 5 | 30 | W5 | Release readiness |

### クリティカルパス (task ID 表記)
T-FND-01 → T-FND-09 → T-001-01 → T-001-02 → T-001-04 → T-001-06 → T-002-01 → T-002-02 → T-003-01 → T-003-02 → T-Mxx-01

### 1 Wave 周期内の実行プラン
- 1 Wave = 数時間 × project-defined parallel capacity
- 完了判定: 各 task の N CI gate auto-merge
- 連続 N 失敗 → human エスカ
- 全 task green で Wave 完了 → 次 Wave 起動

### Group D (Drift fix) 常時 20% の運用
- Backend phase 以降の各 Wave で Group D を常時 20% 割当
- 対象: drift 検出 lint rule 違反 (例: mock-impl-diff / screens-API / entity-table-naming)
- 検出: 前 Wave の merge 時に CI gate が自動検出 → 次 Wave の Group D 候補リストへ
```

**深掘りチェック（STEP 3で必ず確認すること）：**

| チェック項目 | 確認ポイント |
|------------|------------|
| 同じ Wave 内で work-package boundary が衝突していないか | 同一 file への並列 edit は file-level mutex で排他 |
| クライアント確認待ちは Phase gate でのみ計上されているか | Wave 内は CI gate auto-merge。Wave 間は確認待ち 0 |
| Wave 0 (Foundation) の完了ゲートが mechanical / observable に定義されているか | 「準備完了」ではなく N CI gate green と lint 0 件で機械判定 |
| Wave 間の depends_on が DAG.md と整合しているか | 依存違反は Backend phase 開始後に破綻する |
| 各 Wave に Group D (drift fix) 20% が割当されているか | drift 増殖を防ぐため Backend phase 以降常時 |
| 並列度が GitHub Actions / hosting plan の制限内か | 上限超過で CI が直列化するとスケジュール破綻 |
| **UI phase の Wave が対応する Backend phase の Wave 完了後に起動しているか** | UI が先行すると API spec 変更時に手戻りが大きい |

**⛔ STEP 3を出力したら必ずここで止まる。STEP 4には進まない：**

```
---
📅 **STEP 3 確認**
スケジュール詳細を確認してください。
- リソース配置・並列グループのタイミングに無理はありますか？
- クリティカルパスに認識の相違はありますか？
- 問題なければ「STEP 4へ」とお知らせください

※ 回答をいただいてから次のSTEPに進みます
---
```

---

### ▶ STEP 4：リスク・変更管理の設計

確認後、スケジュールが崩れるリスクと、崩れたときの対応方針を整理する。

**出力する内容：**

```
## リスク管理

### スケジュールリスク一覧 (v3)
| リスクID | リスク | 発生確率 | 影響 | 対応策 | トリガー（これが起きたら発動）|
|---------|-------|---------|-----|-------|--------------------------|
| R001 | ブロッキングタスク T-FND-01 が遅延 | 中 | 全体が 1 Wave 遅延 | クリティカルパスにバッファ Wave 追加 | W1 開始までに T-FND-01 系が done でなければアラート |
| R002 | クライアント確認 (Phase gate) が遅延 | 高 | Phase 間のゲートが詰まる | Phase gate 受付から N 営業日後にリマインド | Phase gate フィードバック期限超過 |
| **R-V3-01** | **CI gate 連続失敗 (1 task / N 回 reject)** | 中 | 該当 task の Wave 内処理停止 | N 回で human エスカ + audit MD で原因記録 | 同一 task PR で N 回連続 gate fail |
| **R-V3-02** | **並列セッション競合 (同一 file への並列 edit)** | 中 | merge conflict 多発 | task 分解時に file-level mutex (work-package boundary) | 同 Wave 内で同一 file 編集 task が 2 件以上検出 |
| **R-V3-03** | **drift 増殖 (Group D 滞留)** | 高 | Polish phase 期間が延伸 | Backend phase 以降の Wave で常時 20% を Group D に割当 | drift 検出 lint 違反が前 Wave 末に増加 |
| **R-V3-04** | **Foundation gate 未達のまま Backend phase 開始** | 高 | drift がデフォルト発生 | Wave 0 完了判定を mechanical gate にし Wave 1 起動を機械的 block | Wave 0 の N CI gate が green でない |
| **R-V3-05** | **CI tier (GitHub Actions / hosting plan) 並列上限超過** | 中 | CI 直列化で Wave 周期が延伸 | 並列度を下げる or 有料枠への切替 | 並列実行で queue 待ち > 10 分 |
| **R-V3-06** | **UI phase が Backend phase の API spec 変更で手戻り** | 中 | UI Wave のやり直し | Backend phase 完了後に UI phase Wave を起動 (順序保証) | API spec 変更が UI 着手後に発生 |

### スコープ変更の管理方針
- 追加要望の受付基準：フェーズ完了後のみ受け付ける（開発中は受け付けない）
- 工数が〇日以上の変更：クライアントと書面合意が必要
- 工数が〇日未満の変更：バッファ内で対応・記録する

### 「削れるスコープ」（期限が厳しくなったときの削減候補）
| 機能 | 削除した場合の影響 | 削除の条件 |
|-----|---------------|---------|
| F006（ブログ機能）| ユーザーへの影響：小 | W5時点で全体が2週以上遅延している場合 |

### コミュニケーション計画
| 対象 | 頻度 | 内容 |
|-----|-----|------|
| クライアント | 週次（毎週〇曜日）| 進捗報告・懸念事項・次週の予定 |
| 外部実装者 / 並列セッション | タスク渡し時・返却時 | 仕様確認・完了確認 |
| 社内チーム | 日次スタンドアップ | ブロッカー共有・優先度調整 |
```

**深掘りチェック（STEP 4で必ず確認すること）：**

| チェック項目 | 確認ポイント |
|------------|------------|
| 「リスクが顕在化したと判断するトリガー」は明確か | 「遅れそう」ではなく「〇〇日時点で〇〇が完了していなければ発動」と定義 |
| スコープ変更の受付ルールはクライアントに合意されているか | 開発中に追加が来たとき「それは Polish phase です」と言える状態か |
| コミュニケーション計画にクライアントの承認サイクルが含まれているか | 週次報告だけでなく、フェーズ完了時の正式承認プロセスを定義する |
| 受託契約として「完了の定義」はクライアントと書面合意されているか | 口頭で「大丈夫です」は完了ではない。何をもって納品完了とするかを確認 |

**⛔ STEP 4を出力したら必ずここで止まる。STEP 5（最終出力）には進まない：**

```
---
📅 **STEP 4 確認**
リスク・変更管理の設計を確認してください。
- リスク一覧に追加・変更はありますか？
- スコープ変更の管理方針に同意いただけますか？
- 問題なければ「STEP 5へ」とお知らせください（最終出力を生成します）

※ 回答をいただいてから最終出力を生成します
---
```

---

### ▶ STEP 5：最終出力 (v3: 4 形式同時出力)

「STEP 5へ」の指示を受けたら、以下の 4 形式 (3 既存 + 1 v3 新規 = wave-schedule.json) を一度に出力する。

---

#### 【出力①】スケジュール表（PM・クライアント向け・Markdown）

```
# [プロジェクト名] スケジュール
作成日：YYYY-MM-DD
期間：YYYY-MM-DD 〜 YYYY-MM-DD

## サマリー
- 総期間：〇週間
- フェーズ数：〇フェーズ (Foundation / Backend / UI / Polish, project-defined naming)
- 推定総工数：〇人日（バッファ含む）
- クリティカルパス：T〇〇→T〇〇→T〇〇

## フェーズ別スケジュール
### Foundation phase（〇/〇〜〇/〇）
- 含まれるタスク：〇件
- 推定工数：〇人日
- 納品物：（具体的な成果物）
- クライアント確認内容：（何をどう確認してもらうか）
- 完了条件：（観測可能な状態で定義 / N CI gate green）

### Backend phase（〇/〇〜〇/〇）
（同様）

### UI phase（〇/〇〜〇/〇）
（同様）

### Polish phase（〇/〇〜〇/〇）
（同様）

## Wave 単位スケジュール
（STEP 3のガント表）

## リスク管理
（STEP 4のリスク一覧）
```

---

#### 【出力②】マイルストーンJSON（後続スキル・ツール連携向け）

```json
{
  "project": "プロジェクト名",
  "created_at": "YYYY-MM-DD",
  "total_duration_weeks": 0,
  "phases": [
    {
      "phase": "foundation",
      "name": "Foundation phase",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "duration_weeks": 0,
      "estimated_person_days": 0,
      "tasks": ["T-FND-01", "T-FND-02"],
      "deliverables": [
        "N CI gate green",
        "lint rule 全 0 violation",
        "AC validator 動作確認"
      ],
      "client_review": {
        "what_to_check": "Foundation gate 開放の確認",
        "deadline_business_days": 3,
        "approval_required": true
      },
      "billing_trigger": "Foundation phase 完了承認後"
    }
  ],
  "milestones": [
    {
      "id": "M001",
      "name": "Foundation gate 開放",
      "date": "YYYY-MM-DD",
      "type": "phase_gate",
      "depends_on": ["T-FND-01", "T-FND-02"]
    }
  ],
  "resource_plan": [
    {
      "role": "社内-設計/統合",
      "count": 1,
      "peak_weeks": ["W1", "W4", "W8"]
    }
  ],
  "critical_path": ["T-FND-01", "T-001-01", "T-002-01", "統合完了"]
}
```

---

#### 【出力③ v3 新規】wave-schedule.json (Wave 単位実行プラン)

claude-runner / Swarm / distributed-dev が読んで起動順序を決める JSON:

```json
{
  "version": "v3",
  "skill": "schedule-design",
  "phases": [
    {
      "phase_id": "foundation",
      "name": "Foundation phase",
      "wave_ids": ["W0"],
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "duration_days": 0,
      "completion_gate": "N CI gate 全 pass + lint 0 件 + drift 0 件",
      "phase_review_required": true
    },
    {
      "phase_id": "backend",
      "name": "Backend phase",
      "wave_ids": ["W1", "W2", "W3"],
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "duration_days": 0,
      "completion_gate": "全 Slice の API contract test pass + access control matrix pass",
      "phase_review_required": true
    },
    {
      "phase_id": "ui",
      "name": "UI phase",
      "wave_ids": ["W4", "W5"],
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "duration_days": 0,
      "completion_gate": "全 Slice の UI E2E test pass + a11y pass",
      "phase_review_required": true
    },
    {
      "phase_id": "polish",
      "name": "Polish phase",
      "wave_ids": ["W6"],
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "duration_days": 0,
      "completion_gate": "release readiness checklist 全 pass",
      "phase_review_required": true
    }
  ],
  "waves": [
    {
      "wave_id": "W0",
      "phase_id": "foundation",
      "name": "Foundation: lint / AC validator / CI gate",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "parallel_session_count_target": 10,
      "group_split": {"A": 10, "B": 0, "C": 0, "D": 0},
      "tasks": ["T-FND-01", "T-FND-02", "T-FND-03"],
      "depends_on_waves": [],
      "completion_criteria": [
        "all N CI gates pass (project-defined gate set)",
        "all lint rules 0 violations",
        "AC validator validates 3-tier schema"
      ]
    },
    {
      "wave_id": "W1",
      "phase_id": "backend",
      "name": "Slice 0 backend: auth + base schema",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "parallel_session_count_target": 30,
      "group_split": {"A": 0, "B": 21, "C": 3, "D": 6},
      "tasks": ["T-001-01", "T-001-02"],
      "depends_on_waves": ["W0"],
      "completion_criteria": [
        "auth API contract test pass",
        "base schema migration applied",
        "all access control policies tested"
      ]
    },
    {
      "wave_id": "W4",
      "phase_id": "ui",
      "name": "Slice 0 UI: auth screens + workspace dashboard",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "parallel_session_count_target": 30,
      "group_split": {"A": 0, "B": 21, "C": 3, "D": 6},
      "tasks": ["T-001-10", "T-001-11"],
      "depends_on_waves": ["W1"],
      "completion_criteria": [
        "auth flow E2E pass (login/logout/signup)",
        "workspace dashboard renders KPI",
        "a11y check pass"
      ]
    }
  ],
  "milestones": [
    {
      "milestone_id": "M0",
      "name": "Foundation phase 完了 / Foundation gate 開放",
      "date": "YYYY-MM-DD",
      "depends_on": ["W0"],
      "type": "phase_gate"
    }
  ],
  "ci_gate_auto_merge": {
    "enabled": true,
    "gates": [
      "lint (project-defined rule set)",
      "AC validator (3-tier schema + EARS form)",
      "access control coverage (e.g. RLS verifier)",
      "audit MD existence",
      "test coverage gate (e.g. >= 70%)",
      "type check (e.g. pyright / tsc strict)",
      "mock-impl-diff (drift detector)"
    ],
    "consecutive_failure_threshold": 3,
    "human_escalation_after": 3
  },
  "critical_path": [
    "T-FND-01", "T-FND-09", "T-001-01", "T-001-02",
    "T-002-01", "T-002-02", "T-003-01", "T-003-02"
  ]
}
```

---

#### 【出力④】データ蓄積JSON（判断ログ・MCP連携向け）

```json
{
  "meta": {
    "project": "プロジェクト名",
    "created_at": "YYYY-MM-DD",
    "skill_version": "v3-2026-05-16-generalized",
    "total_phases": 4,
    "total_weeks": 0
  },
  "context": {
    "project_type": "Webアプリ/モバイル/SaaS/社内ツール",
    "team_type": "社内チーム/外部分散/ハイブリッド/並列セッション",
    "client_type": "新規/既存/社内",
    "contract_type": "受託固定/受託準委任/社内開発",
    "parallel_capacity": "small (1-5) / medium (10-30) / large (30-100) / massive (100+)"
  },
  "decision_log": [
    {
      "decision": "Foundation / Backend / UI / Polish の 4 phase 構成にした",
      "reason": "なぜその分け方にしたか",
      "alternatives": ["2フェーズ案", "1括案"],
      "tradeoffs": "トレードオフ"
    }
  ],
  "schedule_patterns": [
    {
      "pattern_name": "パターン名（例：並列セッション Wave 制御）",
      "applicable_to": "どんなプロジェクトに使えるか",
      "description": "効果と適用条件"
    }
  ],
  "risk_log": [
    {
      "risk_id": "R001",
      "risk_type": "ブロッキング遅延/クライアント確認遅延/スコープ変更/CI gate 連続失敗/drift 増殖",
      "description": "リスクの内容",
      "trigger": "何が起きたら発動するか",
      "mitigation": "対応策"
    }
  ],
  "research": {
    "sources": [{"url": "", "title": "", "accessed_at": "YYYY-MM-DD"}],
    "findings": ["調査結果の要点1", "調査結果の要点2"],
    "research_date": "YYYY-MM-DD"
  }
}
```

---

## このスキルの典型的な使い方（受託 / 内製 dogfood / 並列セッション 共通）

```
PM: 「タスク分解ができた。スケジュールを引きたい」
 → STEP 1 を出力（止まる）

PM: 「Foundation / Backend / UI / Polish の 4 phase で。Backend phase は 6 週で認証とコア機能だけ」
 → STEP 2 を出力（止まる）

PM: 「Backend phase の納品物をもう少し具体的にしたい」
 → 調整して再出力（止まる）

PM: 「STEP 3へ」
 → Wave 単位ガント表とリソース配置を出力（止まる）

PM: 「STEP 4へ」
 → リスク・変更管理設計を出力（止まる）

PM: 「STEP 5へ」
 → 4 形式の最終出力 (Markdown / milestones JSON / wave-schedule.json / decision log JSON)
```

**受託開発での重要な原則：**
スケジュールを引く前に必ず「Foundation phase が終わったら何をクライアント (or 自分) に見せるか」「Backend phase 完了で何が動いているか」を決める。
これが決まっていないスケジュールは、設計書ではなく「工数の積み上げ表」でしかない。

---

## 📦 構造化JSON出力仕様（最終ステップのみ）

```devos-json
{
  "project_name": "プロジェクト名",
  "start_date": "2025-01-01",
  "end_date": "2025-06-30",
  "milestones": [
    {"name": "マイルストーン名", "date": "2025-03-01", "deliverables": ["成果物1"], "status": "pending"}
  ],
  "sprints": [
    {"name": "Wave 1", "start": "2025-01-01", "end": "2025-01-14", "goals": ["目標1"], "tasks": ["T-001"]}
  ],
  "risks": [
    {"risk": "リスク内容", "mitigation": "対策", "buffer_days": 5}
  ],
  "resources": [
    {"role": "フロントエンドエンジニア / 並列セッション", "allocation": "100%", "notes": ""}
  ]
}
```
