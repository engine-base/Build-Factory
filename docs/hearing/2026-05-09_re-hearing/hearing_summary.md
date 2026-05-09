# Build-Factory v2 ヒアリングサマリー（再ヒアリング）

**作成日**：2026-05-09
**ヒアリング対象**：高本まさと（info@engine-base.com）
**前回ブリーフ**：`docs/PROJECT_BRIEF.md`（v1, 2026-05-01）→ コンセプト含めて再定義
**ステータス**：STEP 4 完了 → 次は requirements-definition / architecture-design へ

---

## プロジェクト概要

- **作るもの**：Build-Factory（開発工場 OS）
- **本質的なゴール**：ヒアリング → 要件定義 → 設計 → タスク分解 → 実装 → テスト → 進捗管理 → 納品 までを 1 つの Web アプリで完璧に進められる環境
- **本質的な動機**：1 人で 10 案件並走しても破綻しない開発体制を構築し、SaaS 商用化する
- **コンセプトの再定義（v2）**：v1 は「決めるのは人間 / AI が実行」を**コンセプト**にしていたが、これは**設計思想**に過ぎない。コンセプト = **「企画から納品までの全工程を 1 環境で完璧に進めるプロジェクト管理 OS」**

### 成功の定義

**定量**：
- 自社 1 案件を Build-Factory + Claude Code で完走（要件投入 → 納品）
- 1 人で 10 案件を破綻なく並走
- AI 出力差し戻し率 **80% → 20% 以下**
- 1 タスクあたり Token コスト見える化・workspace 上限内
- SaaS マルチテナント・認証・権限が商用提供レベル

**定性**：
- 「もう手放せない」と感じる
- 情報過多にならない（progressive disclosure / role-based view）
- 監視担当が「確認するだけで OK」と言える
- 短期に早く回り、長期で負債を残さない

---

## 制約サマリー

| 項目 | 内容 |
|---|---|
| **期限** | とにかく早く・ただし楽な道に逃げず長期で楽になる確実な作り |
| **予算** | 実装層 LLM = 各自プラン消費 / チャット層 = 自社 API + BYOK 2 系統 / 観測 self-host で低コスト |
| **チーム** | 1 人（まさとさん）+ Claude Code を実装エンジン（dogfooding） |
| **技術スタック** | 自作回避・OSS / SaaS / SDK / ライブラリ最大活用・**商用利用可ライセンス必須**（Apache 2.0 / MIT / BSD / Elastic 2.0）・**AGPL 要注意** |
| **既存システム** | Build-Factory bootstrap（FastAPI 8001 + Next.js 3001 + 96 スキル）は流用、現デザイン感継続。company-dashboard は当面切り離し |
| **情報過多回避** | UI に常に出る情報量を絞る（progressive disclosure / role-based view を最初から織り込み）|
| **データ保護** | account_id / workspace_id を全テーブル必須・Supabase RLS で強制 |

---

## アーキテクチャ全体像（7 レイヤー）

```
┌─────────────────────────────────────────────────────────┐
│ 1. UI レイヤー                                            │
│    Next.js 15 + shadcn/ui + Recharts + React Flow         │
│    HTML/Markdown ハイブリッド出力 + GrapesJS embed        │
│    progressive disclosure / role-based view               │
├─────────────────────────────────────────────────────────┤
│ 2. AI 社員レイヤー（ハイブリッド）                         │
│    BMAD ペルソナ + Anthropic Agent Teams + 既存 96 スキル  │
├─────────────────────────────────────────────────────────┤
│ 3. プロジェクト管理レイヤー（独自 moat）                   │
│    フェーズ管理 / 依存グラフ / 影響分析 / 自動伝搬         │
│    多 view（カンバン / リスト / ガント / DAG / swarm）     │
├─────────────────────────────────────────────────────────┤
│ 4. 実装連携レイヤー                                        │
│    Claude Code（OAuth で各自プラン）+ MCP サーバー         │
│    Anthropic Agent Teams で Plan/Gen/Eval 分離             │
│    ▶︎ 再生 / 並列 swarm / Hermes 風 crash detection       │
├─────────────────────────────────────────────────────────┤
│ 5. 連携レイヤー                                            │
│    Slack（双方向 + Claude Desktop MCP）/ GitHub /          │
│    Obsidian Headless Sync / デプロイ連携アダプタ           │
├─────────────────────────────────────────────────────────┤
│ 6. データ + 認証 + 観測 レイヤー                           │
│    Supabase（Postgres + Auth + RLS + Realtime + Storage）  │
│    Langfuse self-host（観測 + eval + バージョン管理）      │
│    OpenFGA（必要箇所の fine-grained 権限・Phase 2）        │
├─────────────────────────────────────────────────────────┤
│ 7. ナレッジ + LLM レイヤー                                 │
│    Obsidian 母艦 + Mem0 + 自動キュレーション               │
│    LLM: 各自 Claude Pro/Max（実装）/ BYOK or 自社（チャット）│
└─────────────────────────────────────────────────────────┘
```

---

## MVP イメージ（Phase 1 完了時の体験）

```
まさとさんが Build-Factory を開く
  ↓
新規案件作成 → ヒアリング AI 社員（BMAD BA + 既存 hearing スキル）が起動
  ↓
ヒアリング HTML サマリーが workspace に生成（共有可能リンク付き）
  ↓
要件定義 → アーキ設計 → API 設計 → 機能分解 → タスク分解
  各工程で HTML 仕様書 + 依存グラフ自動更新
  ↓
プロジェクトを Phase 1 / 2 に分割（フェーズ管理 UI）
  ↓
タスクカードの ▶︎ 再生ボタン → Build-Factory が Claude Code セッションを起動
  ・仕様書 + acceptance-criteria + 関連ナレッジを初期プロンプトに注入
  ・Anthropic Agent Teams（Planner / Generator / Evaluator）が回る
  ・WebSocket でライブログ表示
  ↓
複数タスク同時 ▶︎ or「Play All」→ 並列セッション起動
  ・依存グラフを尊重（親が未完なら子は ready 待機）
  ・親完了で子が自動 ready 昇格（Hermes 親子昇格）
  ・swarm グリッド view で全セッション同時監視
  ・circuit breaker：N 回連続失敗で自動 block
  ↓
Evaluator PASS → リーダー AI へ → 全タスク完了 → 統合テスト
  ↓
GitHub PR + HTML レビュー資料 → まさとさん承認 → 納品 HTML 生成
  ↓
Slack 完了通知
  ↓
ナレッジが Obsidian に蓄積（成功パターン / 差し戻し履歴 / 失敗）
```

---

## 優先機能 Must（Phase 1：22 項目）

| # | 要件 | 必須理由 |
|---|---|---|
| M-1 | Supabase 基盤移行（SQLite → Postgres + Auth + RLS）| 後で移行はマイグレーションコスト爆発 |
| M-2 | 既存 96 スキル整理（使うものだけ残す） | UI / AI 社員設計が決まらない |
| M-3 | AI 社員ハイブリッド統合（BMAD + Anthropic Agent Teams + 既存）| OS の中核 |
| M-4 | account / workspace / workspace_members 階層 | マルチテナント土台 |
| M-5 | ヒアリング → 仕様書 HTML 出力パイプライン | 1 案件入口 |
| M-6 | 機能・タスク分解 + acceptance-criteria | Claude Code に渡す単位 |
| M-7 | 多 view タスク管理（カンバン + リスト + 依存グラフ React Flow） | 進捗が見えない |
| M-8 | プロジェクト・フェーズ管理基盤 | 案件が回らない |
| M-9 | 依存グラフ + 基本伝搬 | moat の核 |
| M-10a | MCP サーバー（データ流通）| 実装連携入口 |
| M-10b | Claude Code セッション・スポナー（▶︎ 再生）| 主要 UX |
| M-10c | 並列セッション・マネージャ（swarm）| 10 案件並走の前提 |
| M-10d | WebSocket セッション・ストリーミング UI | リアルタイム監視 |
| M-11 | リーダー AI 壁打ちループ（Plan / Gen / Eval）| moat の核 |
| M-12 | 赤線リスト + 自動停止（主要 5 項目） | 安全装置 |
| M-13 | GitHub 連携（PR + HTML diff 注釈レビュー） | 実装フローが閉じる |
| M-14 | Slack 通知（片方向：失敗 / 赤線 / 進捗） | 10 案件並走に必須 |
| M-15 | HTML レポート全種（仕様 / 進捗 / レビュー / 納品物） | 出力資産 |
| M-16 | Obsidian ナレッジ母艦連携（最小：単方向 export） | ナレッジ保管先 |
| M-17 | Langfuse self-host（観測 + コスト把握） | 何が起きているか見える |
| M-18 | 監査ログ + バックアップ | SaaS 商用必須 |
| M-19 | 既存 Build-Factory bootstrap の振り分け実行 | 残す / 改修 / 廃止判定 |

## Should（Phase 1.5：社内拡張で大幅に価値が上がる・10 項目）

| # | 要件 |
|---|---|
| S-1 | クライアント / メンバー招待 + タブ ON/OFF |
| S-2 | Slack 双方向 + Claude Desktop MCP 連携 |
| S-3 | GrapesJS Studio SDK 統合（HTML/CSS GUI 編集） |
| S-4 | Obsidian Headless Sync 双方向 |
| S-5 | impact-analysis + task-propagation スキル（既存実装影響分析） |
| S-6 | BYOK 設定 UI |
| S-7 | AI モデル / プロンプトバージョン管理 |
| S-8 | 通知 / アラートフル（停滞・依存破綻含む） |
| S-9 | ナレッジ自動キュレーション |
| S-10 | crash detection / circuit breaker |

## Could（Phase 2 / 3）

| # | 要件 | フェーズ |
|---|---|---|
| C-1 | OpenFGA 細粒度権限 | Phase 2 |
| C-2 | AI 評価基盤（壁打ち精度 eval） | Phase 2 |
| C-3 | デプロイ連携アダプタ（Vercel / Netlify / Coolify / Cloud Run / 自前 SSH） | Phase 2 |
| C-4 | テンプレート / Boilerplate | Phase 2 |
| C-5 | E2E Playwright MCP 統合 | Phase 2 |
| C-6 | Stripe / Lemon Squeezy 課金 | Phase 3 |
| C-7 | SaaS マルチテナント本格化（SLA / 障害自動監視） | Phase 3 |
| C-8 | 多言語 UI / モバイル最適化 | Phase 3 |
| C-9 | テンプレート Marketplace（コミュニティ共有） | Phase 3+ |

## スコープ外 Won't

| # | 除外 | 理由 |
|---|---|---|
| W-1 | ローカル LLM の SaaS 提供 | self-host モードに限定 |
| W-2 | AI 自身による要件発生 | 信用毀損リスク |
| W-3 | クライアントが UI を直接編集 | 権限管理過剰複雑化 |
| W-4 | Build-Factory が直接本番デプロイ | 必ず人間承認 |
| W-5 | Claude Code 以外の実装エンジン | スコープ拡大（Phase 3 で評価） |
| W-6 | モバイルアプリ版 | Web 完結 |
| W-7 | Onlook / Open Design 統合 | 仕様書 HTML + GrapesJS で代替 |
| W-8 | 案件種別ごとのテンプレート機能 | 汎用設計 + ユーザー作成テンプレで対応 |

---

## ステークホルダー

| 役割 | 関与度 | 期待 / 懸念 |
|---|---|---|
| **まさとさん**（最終決裁・主ユーザ） | 🔴 最高 | 10 案件並走 / SaaS 商用化 / もう手放せない／自分のリソース詰まり |
| **監視担当**（将来・社内 or 業務委託） | 🟡 中 | チェックだけで品質担保／AI ミス見逃し責任 |
| **クライアント**（受託案件先） | 🟡 中 | 進捗が見える・コメント反映が早い／内部 AI に任せて品質低下 |
| **SaaS 顧客**（将来） | 🟢 低 → 🔴 高 | 自社開発 OS として利用／データ分離 / SLA / セキュリティ |
| **AI 社員**（実体は LLM + スキル） | 🔴 実行主体 | 自領域で漏れなく実行／ハルシネーション |
| **Claude Code**（外部実装エンジン） | 🔴 実行 | 与えられた仕様で実装／仕様の曖昧さ |
| **OSS / SaaS 提供元** | 🟢 観察 | OSS のライセンス変更・メンテ停止・破壊的変更 |
| **company-dashboard** | 🟡 並走（当面切り離し） | UI 整理 / データ重複回避 |

---

## 主要決定（Decision Log の要約）

| # | 決定 | 理由 |
|---|---|---|
| D-1 | v1 PROJECT_BRIEF を白紙化、コンセプトを再定義 | 「人間 / AI 役割分担」は設計思想に過ぎない・本質は「全工程 1 環境」 |
| D-2 | Onlook / Open Design 不採用 | 仕様書 → HTML/CSS で完璧再現 + GrapesJS GUI 編集に置き換え |
| D-3 | 出力フォーマット = HTML + Markdown ハイブリッド（HTML デフォルト） | Thariq Shihipar の Anthropic 内主流に追随・情報密度・共有性 |
| D-4 | タスク ▶︎ 再生 + 並列実行 + swarm view | Hermes Specify + Vibeyard swarm を Web 化 |
| D-5 | 自作回避・OSS / SaaS / SDK 最大活用 | 開発スピード + 保守負担削減 |
| D-6 | 商用利用可ライセンスのみ採用（Apache 2.0 / MIT / BSD / Elastic 2.0） | SaaS 商用化前提 |
| D-7 | 実装層 LLM = 各自 Claude Pro/Max プラン | コスト分散・SaaS 限界利益向上 |
| D-8 | チャット層 LLM = 自社 API + BYOK の 2 系統 | ユーザー柔軟性 |
| D-9 | ローカル LLM は SaaS では提供しない（self-host モードのみ） | スコープ絞り込み |
| D-10 | 認証 = Supabase Auth | DB と統一・RLS で multi-tenant 強制 |
| D-11 | DB = Supabase Postgres（SQLite から移行） | SaaS 化に必要・RLS が moat |
| D-12 | AI 社員 = BMAD ペルソナ + Anthropic Agent Teams + 既存スキル ハイブリッド | 既存資産活用 + 公式パターン採用 |
| D-13 | デプロイ環境 = 連携アダプタ式（複数選択可） | ユーザー自由度 |
| D-14 | ナレッジ = Obsidian 母艦 | まさとさん既存運用との統合 |
| D-15 | 観測 = Langfuse self-host | コスト最小・MIT |
| D-16 | プロジェクト・フェーズ管理 + 依存グラフ + 影響分析 = moat | Linear / Jira / Notion にない領域 |
| D-17 | 既存 Build-Factory bootstrap は流用、現デザイン感継続 | 短期速度・既存資産活用 |
| D-18 | company-dashboard は当面切り離し（将来追加可能性） | スコープ絞り込み |
| D-19 | クライアント招待 = Phase 1 から組み込む | 受託案件で外部見せ早期必要 |
| D-20 | Phase 1 Must = 22 項目（▶︎ + 並列 swarm まで含む・後ろ倒さない） | 楽に逃げない方針 |

---

## 未解決の不明点（次のフェーズで確認）

| # | 不明点 | 重要度 | 解決先 |
|---|---|---|---|
| 1 | Phase 1 Must 22 項目の各タスク見積もり工数 | high | task-decomposition |
| 2 | BMAD のどの部分を取り込むか（fork / 思想 / 完全採用） | high | architecture-design |
| 3 | Anthropic Agent Teams の最新 API 仕様確認 | high | architecture-design |
| 4 | GrapesJS Studio SDK の商用ライセンス費用 | medium | tech-stack |
| 5 | Supabase 移行時の既存 SQLite データ取り扱い | high | architecture-design |
| 6 | リーダー AI 壁打ちの「3 ターン」の具体実装 | medium | feature-decomposition |
| 7 | 並列セッション数の現実的上限（プラン別） | medium | tech-stack |
| 8 | クライアント招待 UI のメール文面 / 招待 URL 設計 | low | feature-decomposition |
| 9 | Obsidian Headless Sync の Phase 1 での簡易代替（単方向）の実装 | medium | architecture-design |
| 10 | 削除する既存 router / service の最終リスト | high | feature-decomposition |

---

## 次のアクション（推奨）

1. **requirements-definition** スキルで M-1〜M-19 を要件として詳細化
2. **architecture-design** スキルで Supabase 移行 + AI 社員ハイブリッド統合の技術設計
3. **tech-stack** スキルで OSS 候補の最終選定（BMAD / Anthropic Agent Teams / GrapesJS / etc.）
4. **functional-breakdown** スキルで画面・機能・ロール権限・エンティティ草案
5. **feature-decomposition** + **task-decomposition** で Phase 1 を実装単位に分解
6. **distributed-dev** で各タスクを Claude Code が単独実装できるパッケージに

---

## 関連ファイル

- `hearing_summary.html`（HTML 版・SVG 図解付き）
- `project_brief.json`（後続スキル引き継ぎ用構造化データ）
- `decision_log.json`（判断ログ + Web リサーチ findings）
- `../../PROJECT_BRIEF.md`（v1, 2026-05-01・参照履歴）
- `../../PROJECT_BRIEF_v2.md`（v2 マスター仕様書・このセッション後に作成可能）
