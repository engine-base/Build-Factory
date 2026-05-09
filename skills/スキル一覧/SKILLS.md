# ENGINE BASE — スキル一覧

全18スキル。受託開発の全工程をカバーする「開発OS」。

---

## フロー図

```
[受注前]
  ① hearing → ② requirements-definition → ③ product-strategy
                                                  ↓
                              ★ ⑲ tech-stack（技術スタック選定）
                              ↙                  ↓
  ④ proposal ＋ ⑤ estimate（並行）               ↓
                                                  ↓
[設計]
  ⑥ design-foundation → ⑧ ui-mockup
  ⑦ architecture-design（tech-stackの出力を受け取る）
       → ⑨ feature-decomposition → ⑩ api-design
                                                  ↓
[開発準備]
  ⑪ task-decomposition → ⑫ schedule-design
                                                  ↓
[開発]
  ⑬ distributed-dev → ⑭ integration
                                                  ↓
[品質・納品・運用]
  ⑮ test-verification → ⑯ delivery → ⑰ operations

[マーケティング（独立）]
  ⑱ write-article

★ ⑲ tech-stack は product-strategy 後・architecture-design 前に実施。
   proposal の技術説明欄にも利用可。
```

---

## スキル一覧表

| # | スキル名（ファイル） | フェーズ | 主な呼び出しフレーズ | Claudeへのコマンド例 |
|---|----------------|---------|------------------|-------------------|
| ① | `hearing` | 商談 | 「ヒアリングしたい」「商談したい」「要件を聞き出したい」「最初の打ち合わせをしたい」「プロジェクトを始めたい」 | `hearing スキルを起動して。クライアントは〇〇、目的は〇〇` |
| ② | `requirements-definition` | 設計 | 「要件定義したい」「仕様をまとめたい」「機能を整理したい」「アプリを作りたい」 | `requirements-definition スキルを起動。hearing出力を貼り付け` |
| ③ | `product-strategy` | 設計 | 「MVPを決めたい」「フェーズ分けしたい」「優先順位をつけたい」「ロードマップを作りたい」「スコープを絞りたい」 | `product-strategy スキルを起動。要件定義出力を貼り付け` |
| ④ | `proposal` | 受注前 | 「提案書を作りたい」「プレゼン資料を作りたい」「ヒアリング後の提案をまとめたい」「クライアントに見せる資料を作りたい」 | `proposal スキルを起動。hearing/要件定義/product-strategy出力を貼り付け` |
| ⑤ | `estimate` | 受注前 | 「見積書を作りたい」「金額をまとめた書類を作りたい」「費用の内訳を正式にまとめたい」「見積もりを送りたい」 | `estimate スキルを起動。提案書の金額・項目情報を貼り付け` |
| ⑥ | `design-foundation` | 設計 | 「デザインを決めたい」「カラーパレットを作りたい」「UIルールを統一したい」「デザインシステムを作りたい」「Tailwind設定を作りたい」 | `design-foundation スキルを起動。プロジェクト概要を貼り付け` |
| ⑦ | `architecture-design` | 設計 | 「アーキテクチャを決めたい」「DB設計をしたい」「インフラ構成を決めたい」「モノリスかマイクロか判断したい」「システム構成を固めたい」 | `architecture-design スキルを起動。要件定義・product-strategy・tech-stack出力を貼り付け` |
| ⑧ | `ui-mockup` | 設計 | 「モックアップを作りたい」「画面イメージをHTMLで確認したい」「クライアントに画面を見せたい」「ワイヤーフレームをブラウザで確認したい」 | `ui-mockup スキルを起動。design-foundation出力とページ一覧を貼り付け` |
| ⑨ | `feature-decomposition` | 開発準備 | 「機能を分解したい」「並列開発できるようにしたい」「依存関係を整理したい」「エンジニアにタスクを振りたい」 | `feature-decomposition スキルを起動。要件定義・architecture-design出力を貼り付け` |
| ⑩ | `api-design` | 開発準備 | 「APIを設計したい」「エンドポイントを決めたい」「リクエスト/レスポンスの型を定義したい」「OpenAPI仕様を作りたい」「バックエンドとフロントのI/Fを決めたい」 | `api-design スキルを起動。機能分解・architecture-design出力を貼り付け` |
| ⑪ | `task-decomposition` | 開発準備 | 「タスクに分けたい」「チケット化したい」「実装単位を明確にしたい」「誰が何をやるか決めたい」「受け入れ条件を決めたい」 | `task-decomposition スキルを起動。機能分解・API設計出力を貼り付け` |
| ⑫ | `schedule-design` | 開発準備 | 「スケジュールを引きたい」「工数見積もりを出したい」「マイルストーンを決めたい」「フェーズごとの納品物を決めたい」「請求タイミングを決めたい」 | `schedule-design スキルを起動。タスク分解出力を貼り付け` |
| ⑬ | `distributed-dev` | 開発 | 「Claude Codeに実装させたい」「ブランチを切って渡したい」「実装者に情報を最小限で渡したい」「監視役として進めたい」 | `distributed-dev スキルを起動。タスクカードを貼り付け` |
| ⑭ | `integration` | 開発 | 「ブランチをマージしたい」「統合を進めたい」「コンフリクトが怖い」「リリース前の最終チェックをしたい」 | `integration スキルを起動。マージ対象ブランチ一覧を貼り付け` |
| ⑮ | `test-verification` | 品質 | 「テスト戦略を決めたい」「品質基準を設けたい」「CIを整備したい」「テストを書きたい」「リグレッションを防ぎたい」 | `test-verification スキルを起動。機能一覧・architecture-design出力を貼り付け` |
| ⑯ | `delivery` | 納品 | 「納品したい」「検収の進め方を決めたい」「受け入れテストを設計したい」「引き継ぎを整理したい」「納品後のサポート範囲を決めたい」 | `delivery スキルを起動。納品物リストとスケジュール出力を貼り付け` |
| ⑰ | `operations` | 運用 | 「運用体制を決めたい」「障害対応手順を作りたい」「保証期間の範囲を決めたい」「改善提案の仕組みを作りたい」「監視設定をしたい」 | `operations スキルを起動。delivery出力とシステム構成を貼り付け` |
| ⑱ | `write-article` | マーケ | 「記事を書きたい」「SEO記事を作りたい」「ブログを書きたい」「コンテンツマーケをしたい」 | `write-article スキルを起動。テーマ・ターゲット・誘導先URLを伝える` |
| ⑲ | `tech-stack` | 設計 | 「技術スタックを決めたい」「何で作る？」「フロントとバックは？」「ノーコードと有りコードどっちがいい？」「インフラどうする？」「推奨技術を教えて」 | `tech-stack スキルを起動。プロジェクト概要・予算・期間・運用体制を貼り付け` |

---

## スキルファイル（.skill）の場所

```
/Users/masato0420/Documents/skills/
├── hearing.skill
├── requirements-definition.skill
├── product-strategy.skill
├── proposal.skill
├── estimate.skill
├── design-foundation.skill
├── architecture-design.skill
├── ui-mockup.skill
├── feature-decomposition.skill
├── api-design.skill
├── task-decomposition.skill
├── schedule-design.skill
├── distributed-dev.skill
├── integration.skill
├── test-verification.skill
├── delivery.skill
├── operations.skill
├── write-article.skill
└── tech-stack.skill        ← 新規作成（⑲）
```

---

## スキル間の入出力

| スキル | 主な入力 | 主な出力（次スキルへ渡すもの） |
|-------|---------|---------------------------|
| hearing | 会話・ヒアリング内容 | ヒアリングサマリー・プロジェクト起点JSON |
| requirements-definition | hearing出力 | 要件定義書・MoSCoW表・判断ログJSON |
| product-strategy | requirements-definition出力 | MVPスコープ・フェーズ設計・KPI・判断ログJSON |
| proposal | hearing + requirements + product-strategy | 提案書（Markdown）・HTMLスライド・提案JSON |
| estimate | proposal の金額・項目 | 見積書（Markdown）・印刷対応HTML見積書 |
| design-foundation | プロジェクト概要・ブランド方針 | デザイントークンJSON・Tailwind設定・コンポーネント仕様 |
| architecture-design | requirements + product-strategy | アーキテクチャ仕様書・技術スタックJSON・判断ログ |
| ui-mockup | design-foundation出力 + 画面一覧 | 各画面の独立HTMLモックアップ |
| feature-decomposition | requirements + architecture-design | 機能分解一覧・依存関係マップJSON |
| api-design | feature-decomposition + architecture-design | API仕様書・OpenAPI YAML・TypeScript型定義 |
| task-decomposition | feature-decomposition + api-design | タスクカード一覧・タスクJSON |
| schedule-design | task-decomposition出力 | スケジュール表・マイルストーンJSON・納品物定義JSON |
| distributed-dev | タスクカード | Claude Code実装ブリーフ・CLAUDE.md・ブランチ設定 |
| integration | 完了済みブランチ一覧 | マージ手順書・統合テスト計画 |
| test-verification | 機能一覧 + architecture-design | テスト戦略書・CI設定・カバレッジ基準 |
| delivery | 納品物リスト + スケジュール | 納品チェックリスト・検収定義JSON・引き継ぎパッケージ |
| operations | delivery出力 + システム構成 | 運用マニュアル・監視設計・インシデント対応フロー |
| write-article | テーマ・ターゲット・サービスURL | SEO記事（Markdown）・メタ情報 |
| tech-stack | プロジェクト概要・予算・期間・運用体制・requirements-definition出力 | 推奨スタック提案書（Markdown）・selected-stack.json（architecture-design への引き継ぎ用） |

---

*最終更新：2026-04-17*
