# Build-Factory v2.1 要件定義書

**バージョン**: 1.0（仮説ベース・打ち合わせで確定する項目あり）
**作成日**: 2026-05-09
**作成者**: 株式会社 ENGINE BASE 高本 まさと（27 歳）
**前提ドキュメント**: `docs/hearing/2026-05-09_re-hearing/` (v2.1)

---

## 1. プロジェクト概要

### 目的
**Build-Factory（開発工場 OS）** = 企画から納品までの全工程を 1 つの Web アプリで完璧に進められる SaaS 型開発 OS。

> AI 開発が流行する一方、管理 / 品質の不足で「漏れ」「使えないものになる」事故が頻発している。Build-Factory はこの管理・品質の壁を AI チームと管理盤の一体化で破壊する。

**本質的なゴール**: 1 人で 10 案件並走（1 案件 5 並列タスク）しても破綻しない開発体制を作り、SaaS 商用化する。

### 現状の課題
| 課題 | 影響 |
|---|---|
| 1 人で複数案件並走で context switch コスト爆発 | 案件遅延 / 体力消耗 / 品質低下 |
| AI 出力の 8 割が微妙で結局自分で直す | 時間が節約にならない |
| 要件 → 仕様化が遅い | 案件初動が重い |
| 進捗の見えなさ | 自分で確認するコスト増 |
| 品質保証の属人化 | スケールしない |
| ナレッジが活用されていない | 過去案件の学びが流れる |
| 既存ツール（Linear / Notion / Devin / Cursor）が断片的 | 管理盤と実装エンジンが分断 |
| company-dashboard がわかりづらい | 使われない / 整理が必要 |

### 制約
| 種別 | 内容 |
|---|---|
| 期限 | とにかく早く・楽な道に逃げず長期で楽になる確実な作り |
| 予算 | 実装層 LLM = 各自プラン消費 / チャット層 = 自社 API + BYOK 2 系統 / 観測 self-host |
| チーム | 1 人（高本まさと）+ Claude Code を実装エンジン（dogfooding） |
| 技術 | 自作回避・OSS 最大活用・**Apache 2.0 / MIT / BSD / Elastic 2.0 のみ** |
| 既存システム | Build-Factory bootstrap 流用 / company-dashboard は当面切り離し |
| 法的 | 下請法・個人情報保護法・NDA・秘密保持義務 |

### 技術スタック
| 層 | 採用技術 |
|---|---|
| Frontend | Next.js 15 + shadcn/ui + Recharts + React Flow + GrapesJS Studio SDK（P1.5） |
| Backend | FastAPI（既存継続）+ Supabase クライアント |
| DB | Supabase Postgres + RLS |
| 認証 | Supabase Auth |
| Storage | Supabase Storage |
| Realtime | Supabase Realtime + WebSocket |
| AI 社員 | BMAD ペルソナ + Anthropic Agent Teams + 既存 96 スキル ハイブリッド |
| LLM 抽象化 | LiteLLM ベース（Claude / OpenAI / Gemini / 拡張容易） |
| 実装層 LLM | 各ユーザの Claude Pro/Max（OAuth） |
| 観測 | Langfuse self-host |
| RBAC | Supabase RLS + custom_permissions JSON / OpenFGA（P2） |
| ナレッジ | Obsidian 母艦（単方向 P1 / 双方向 P1.5） |
| 連携 | Slack Bolt / GitHub MCP / Claude Desktop MCP / Mem0 |
| デプロイ | Coolify / Vercel / Netlify / Cloud Run / SSH 連携アダプタ（P2） |
| 課金 | Stripe / Lemon Squeezy（P3） |

---

## 2. ターゲットユーザー

### ペルソナ
| ID | 名前 | 関与度 | 概要 |
|---|---|---|---|
| P-1 | 高本まさと（自社） | 🔴 最高 | **27 歳** / 1 名運営代表 / 10 案件並走 / dogfood 主ユーザ |
| P-2 | 受託会社 PM / シニアエンジニア | 🔴 高 (P2 主顧客) | 30〜40 代 / 案件 5〜10 並行 / 受託の収益性向上 |
| P-3 | 中小企業の開発リーダー | 🔴 高 (P2 主顧客) | 30〜50 代 / メンバー 2〜10 人 / 属人化解消 |
| P-4 | 個人開発者 / 副業エンジニア | 🟡 中 (P2) | 副業 + 本業 / Pro 1 契約で最大効率 |
| P-5 | 監視担当 | 🟡 中 (内部ロール) | チェックだけで品質担保 |
| P-6 | クライアント（招待） | 🟡 中 | 進捗確認 / コメント反映 |

### ロール（6 種 + custom_permissions）
| ロール | デフォルト権限 |
|---|---|
| `account_owner` | 全権限（課金含む） |
| `workspace_admin` | workspace 内ほぼ全権限 |
| `contributor` | 編集 + 実行 + 承認 + 閲覧 |
| `viewer` | 閲覧のみ |
| `client` | 招待タブのみ閲覧 + コメント |
| `monitor` 🆕 | 全閲覧 + 承認（PR / 赤線 / 納品） |

→ custom_permissions JSON で**全ロール**の個別 override 可能

---

## 3. 主要機能一覧（Phase 1 Must = 30 項目）

| ID | 機能 | カテゴリ | 種別 |
|---|---|---|---|
| M-1 | Supabase 基盤構築 + テストデータ seed | 基盤 | Must |
| M-2 | 既存 96 スキル整理 | 基盤 | Must |
| M-3 | AI 社員ハイブリッド統合（BMAD + Agent Teams + 既存） | AI | Must |
| M-4 | account / workspace / workspace_members 階層 | 基盤 | Must |
| M-5 | ヒアリング → 仕様書 + 画面モック HTML 出力パイプライン | 仕様化 | Must |
| M-5b | 画面モック自動生成パイプライン（画面 + コンポーネント単位） | 仕様化 | Must |
| M-6 | 機能・タスク分解 + acceptance-criteria（EARS notation） | 仕様化 | Must |
| M-7 | 多 view タスク管理（Kanban + List + DAG） | プロジェクト管理 | Must |
| M-8 | プロジェクト・フェーズ管理基盤 | プロジェクト管理 | Must |
| M-9 | 依存グラフ + 基本伝搬 | プロジェクト管理 | Must |
| M-10a | MCP サーバー（データ流通） | 実装連携 | Must |
| M-10b | Claude Code セッション・スポナー（▶︎ 再生） | 実装連携 | Must |
| M-10c | 並列セッション・マネージャ（1 案件 5 並列 + swarm） | 実装連携 | Must |
| M-10d | WebSocket セッション・ストリーミング UI | 実装連携 | Must |
| M-11 | リーダー AI 壁打ちループ（Plan / Gen / Eval） | 品質 | Must |
| M-12 | 赤線リスト + 自動停止（主要 5 項目） | 安全 | Must |
| M-13 | GitHub 連携（PR + HTML diff 注釈） | 連携 | Must |
| M-14 | Slack 通知（片方向） | 連携 | Must |
| M-15 | HTML レポート全種（仕様 / 進捗 / レビュー / 納品物 + 画面モック / カタログ / 遷移マップ） | 仕様化 | Must |
| M-16 | Obsidian ナレッジ母艦連携（単方向 export） | 連携 | Must |
| M-17 | Langfuse self-host（観測 + コスト把握） | 運用 | Must |
| M-18 | 監査ログ + バックアップ | 運用 | Must |
| M-19 | 既存 bootstrap 振り分け実行 | 整理 | Must |
| M-20 | LLM プロバイダー抽象化（Claude / OpenAI / Gemini / 拡張容易） | AI | Must |
| M-21 | ロール custom_permissions UI + monitor ロール | 権限 | Must |
| M-22 | AI 社員 3 階層対応 + 個人ナレッジ namespace | AI | Must |
| M-23 | アカウント設定 / プロフィール画面 | UX | Must |
| M-24 | グローバル検索（Cmd+K） | UX | Must |
| M-25 | EARS notation 標準（acceptance-criteria テンプレ） | 仕様化 | Must |
| M-26 | Constitution（プロジェクト不変原則）= 赤線リスト拡張 | 安全 | Must |

### Should（Phase 1.5 = 12 項目）
S-1 招待 + タブ ON/OFF / S-2 Slack 双方向 + Claude Desktop MCP / S-3 GrapesJS Studio SDK / S-4 Obsidian Headless Sync 双方向 / S-5 impact-analysis + task-propagation / S-6 BYOK 設定 UI / S-7 AI モデル / プロンプトバージョン管理 / S-8 通知・アラートフル / S-9 ナレッジ自動キュレーション / S-10 crash detection 完成 / S-11 部署リーダー AI / S-12 オンボーディング

### Could（Phase 2 / 3 / Future = 11 項目）
C-1 OpenFGA / C-2 AI 評価基盤 / C-3 デプロイ連携アダプタ / C-4 テンプレート / C-5 E2E Playwright MCP / C-10 COO AI（P2）/ C-6 課金 / C-7 SaaS マルチテナント本格化 / C-8 i18n / モバイル / C-9 Marketplace / C-11 個人クローン化サービス（Future）

### Won't（8 項目）
W-1 ローカル LLM の SaaS 提供 / W-2 AI 自身の要件発生 / W-3 クライアント直接 UI 編集 / W-4 直接本番デプロイ / W-5 Claude Code 以外の実装エンジン / W-6 モバイルアプリ版 / W-7 Onlook / Open Design / W-8 案件種別ごとテンプレート

---

## 4. 機能要件詳細

詳細は `requirements_internal.json` を参照。各機能で以下を定義済み：
- 概要 / 入力 / 出力 / 処理の流れ / エラーケース / 制約 / 必要権限

特に重要な機能の概要：

### M-1 Supabase 基盤構築（v2.1 改訂）
- 既存ユーザ移行なし、0 から新規セットアップ
- テストデータ seed：test_account_owner / 6 ロール test_user / 5 sample task / 3 sample artifact / 2 sample AI 社員
- production では seed 走らない（`BF_ENV=development` のみ）

### M-3 AI 社員ハイブリッド統合
- BMAD 12 ペルソナ（Mary BA / Preston PM / Winston Architect / Sally PO / Simon SM / Devon Dev / Quinn QA 等）思想流用
- Anthropic Agent Teams で Plan / Gen / Eval 分離
- 既存 96 スキルから取捨選択
- 3 階層対応（hierarchy_level: csuite / lead / member / personal_clone）

### M-5 + M-5b 仕様書 + 画面モック HTML パイプライン
- 仕様書 HTML（Tailwind + SVG 図解）+ Markdown 併記
- 画面モック HTML（画面ごと 1 ファイル + コンポーネントカタログ + 画面遷移マップ）
- 各モックに「該当仕様へのリンク」「使用コンポーネント一覧」を埋込
- Phase 1.5 で GrapesJS Studio SDK 統合 → ブラウザ上で編集可

### M-6 機能・タスク分解 + EARS notation
- functional-breakdown → feature-decomposition → task-decomposition の連鎖
- acceptance-criteria は EARS 5 形式で必須化（Ubiquitous / Event / State / Optional / Unwanted）
- 1 タスク = 1 セッションで完了する粒度（独立性 KPI 90%）

### M-10b/c/d 実装連携（▶︎ + 並列 swarm + WebSocket）
- ▶︎ ボタン → Claude Code セッション起動（OAuth で各自プラン）
- 1 案件 5 並列タスク / 完了次第キューから自動補充
- 親子昇格（依存グラフ尊重）+ circuit breaker（連続失敗で auto-block）
- swarm グリッド view 16 セッション同時表示（仮想化で 64）

### M-11 リーダー AI 壁打ちループ
- Anthropic Agent Teams Plan / Gen / Eval 分離
- リーダー AI が「タスク粒度妥当 / 依存遵守 / コードスタイル / Constitution 遵守」を評価
- 3 ターン改善なしで人間エスカレ（Slack DM + UI バッジ）

### M-12 + M-26 安全装置（赤線 + Constitution）
- 主要 5 項目自動停止：API キー漏洩 / 本番 DB 破壊 / GitHub force push / AI 無限ループ / デプロイ独断
- Constitution = プロジェクト不変原則 Markdown / 全 AI セッションが context として参照
- 違反検出 → 自動停止 → 監視 / admin 承認待ち

### M-20 LLM プロバイダー抽象化
- LiteLLM ベース推奨
- Claude / OpenAI / Gemini / 軽量 LLM / ローカル LLM（self-host のみ）
- ユーザがプロバイダー + モデルを選択可
- BYOK + 自社提供 API の 2 系統
- 新規プロバイダー追加は adapter 1 ファイル + 設定で完結

### M-22 AI 社員 3 階層対応 + 個人ナレッジ namespace
- ai_employees テーブル拡張：hierarchy_level / parent_employee_id / cloned_from_user_id / department
- user_knowledge_namespace + user_interaction_log 新設（クローン化学習素地）
- 組織図 UI 簡易版（React Flow tree）
- 個人クローン化（C-11）は将来別アプリ・データ蓄積は Phase 1 から（opt-in 必須）

---

## 5. 非機能要件

| 種別 | 要件 |
|---|---|
| パフォーマンス（応答） | UI sub-100ms / セッション起動→出力 10 秒以内（中央値 5 秒） / WebSocket 100ms 以内 |
| パフォーマンス（並列） | 1 案件 5 並列 / 10 案件並走 / グローバル検索 500ms 以内 |
| パフォーマンス（描画） | 1 view 1000 タスクまで快適 / DAG 数百ノード / swarm グリッド 16〜64 |
| セキュリティ（通信） | HTTPS / wss:// / Cloudflare 経由 |
| セキュリティ（認証） | Supabase Auth JWT / 2FA / OAuth / session 24h |
| セキュリティ（認可） | RLS + 6 ロール + custom_permissions / Phase 2 で OpenFGA |
| セキュリティ（機密） | API キー pgsodium 暗号化 / NDA workspace 機密ラベル / 取得時フィルタ |
| セキュリティ（赤線）| 5 項目自動停止 + Constitution + 監査ログ |
| 可用性 | P1: 99% / P2: 99.5% / P3: 99.9% |
| 拡張性 | 1 account 1000 ユーザ / 100 workspace / workspace 1000 タスク快適 |
| データ保護 | 監査ログ 7 年 / DB 日次 90 日 / Storage 週次 / Obsidian リアルタイム |
| 障害許容度 | 1 ユーザ中断は許容 / 全 workspace 不可は不許容 |
| アクセシビリティ | WCAG 2.1 AA / aria-* / キーボード完全対応 |
| 国際化 | P1: ja-JP / P3: en-US |
| ブラウザ | Chrome / Edge / Safari / Firefox 最新 2 / モバイル P3 |
| コンプライアンス | 下請法 / 個人情報保護法 / NDA / P3 で SOC 2 検討 |
| 観測 | Langfuse self-host で全 LLM 呼び出し trace |

---

## 6. 画面・UX 概要

### 画面一覧（Phase 1 = 35 画面）

#### 認証系（5）
login / signup / password_reset / mfa_setup / oauth_callback

#### アカウント横断（6）
account_dashboard（10 案件俯瞰）/ account_settings / account_members / profile_settings / notifications_inbox / global_search

#### Workspace 横断（4）
workspace_dashboard / workspace_settings / workspace_members / workspace_invite

#### プロジェクト管理 moat（4）
phase_management / dependency_graph / constitution_editor / red_line_settings

#### 仕様化・モック（7）
hearing_session / requirements_editor / spec_viewer / **screen_mock_viewer** / **component_catalog** / **screen_flow_map** / design_html_editor（P1.5）

#### タスク・実行（6）
task_kanban / task_list / task_dag_view / task_detail / swarm_grid / swarm_session_detail

#### レビュー・納品（3）
pr_review / red_line_approval / delivery_approval

#### AI 社員・スキル（3）
ai_employees_org_chart / ai_employee_detail / skill_manager

#### ナレッジ・観測（3）
knowledge_base / cost_dashboard / audit_log_viewer

#### クライアント専用（2）
client_workspace（タブ ON/OFF 制限） / client_comment

### 主要ユーザーフロー
1. **新規案件キックオフ → 納品**（メインフロー）
2. **朝のルーティン**（10 案件並走時）
3. **並列実行 + 監視**（swarm）
4. **赤線抵触 → 承認**
5. **クライアント招待 → コメント → 反映**

---

## 7. データ構造（主要 30 テーブル）

### 認証・テナント（6）
accounts / account_members / workspaces / workspace_members / workspace_invitations / users

### AI 社員・スキル（5）
ai_employees / skills / skill_executions / user_knowledge_namespace / user_interaction_log

### プロジェクト管理 moat（6）
phases / phase_gates / tasks / task_dependencies / acceptance_criteria / constitutions

### 仕様・モック（5）
artifacts / artifact_versions / screens / components / screen_components

### 実装・レビュー（7）
sessions / session_logs / session_artifacts / prs / pr_reviews / red_lines / red_line_violations

### 連携・運用（11）
llm_providers / api_keys / slack_webhooks / github_repos / obsidian_vaults / notifications / cost_logs / token_limits / audit_logs / backups

詳細は `requirements_internal.json` を参照。

---

## 8. 外部連携

Supabase / Anthropic Claude（OAuth + Pro/Max）/ OpenAI / Google Gemini / LiteLLM / Langfuse / Slack（片方向 P1 → 双方向 P1.5）/ GitHub / Obsidian / Mem0 / GrapesJS Studio SDK（P1.5）/ Claude Desktop MCP（P1.5）/ OpenFGA（P2）/ デプロイ環境連携（P2）/ Playwright MCP（P2）/ Stripe（P3）/ Cloudflare

---

## 9. リスク・懸念点

主要リスク 43 件のうち、特に重要な 8 件：

| ID | リスク | 影響 | 対応 |
|---|---|---|---|
| R-1 | Supabase 0 セットアップ時のスキーマ設計ミス | 高 | DDL レビュー + RLS テスト + seed で全権限パターン検証 |
| R-2 | LLM ハルシネーション | 高 | 多層検証（M-3 → M-11 → 統合テスト）+ monitor 承認 |
| R-8 | 1 人開発の負荷（Phase 1 = 30 Must） | **高** | dogfooding（BF 自体を BF + Claude Code で開発） + 着手順序最適化 |
| R-10 | 機密情報の workspace 横断リーク | 高 | RLS + 機密ラベル + 監査ログ + AI 取得時フィルタ |
| R-13 | フェーズ管理が現場で使われない | 中 | Phase 1 で自社案件 dogfooding して即改善 |
| R-15 | LLM プロバイダー抽象化で機能差吸収不足 | 中 | capability flag で明示的に扱う |
| R-17 | 個人クローン化の倫理 / プライバシー | 高 | opt-in 必須 + namespace 完全分離 + 別サービス切出し |
| - | dogfooding 自己再帰問題（BF バグで開発停止） | 中 | bootstrap を「動く土台」として残す + Claude Code 単独でも開発可 |

詳細は `requirements_decision_log.json` の risks 配列参照。

---

## 10. 未確認事項・今後の確認事項

| # | 項目 | 優先度 | 解決先 |
|---|---|---|---|
| 1 | BMAD のどの部分を取り込むか | 🔴 | architecture-design |
| 2 | Anthropic Agent Teams 最新 API 確認 | 🔴 | architecture-design |
| 4 | 削除する既存 router / service 最終リスト | 🔴 | feature-decomposition |
| 5 | LLM プロバイダー抽象化の具体（LiteLLM / 自前 / openrouter）| 🔴 | tech-stack |
| 6 | GrapesJS Studio SDK 商用ライセンス費 | 🟡 | tech-stack |
| 7 | EARS notation 具体テンプレ | 🟡 | feature-decomposition |
| 8 | Constitution と赤線リストの統合方法 | 🟡 | architecture-design |
| 9 | 部署リーダー AI / COO AI のスキル構成 | 🟡 | feature-decomposition |
| 10 | 並列セッション現実的上限（実測） | 🟡 | tech-stack（PoC） |
| 11 | リーダー AI 壁打ち 3 ターン具体実装 | 🟡 | feature-decomposition |
| 12 | Phase 1 Must 30 項目の見積もり工数 | 🔴 | task-decomposition |
| 14 | Obsidian P1 簡易代替の実装方式 | 🟡 | architecture-design |
| 16 | Supabase plan 確定（無料 / Pro / Team）| 🟡 | tech-stack |
| 18 | 赤線リスト 5 項目の最終確定 | 🟡 | feature-decomposition |
| 19 | AI プロバイダーの DPA 確認 | 🟡 | tech-stack |

詳細は `requirements_decision_log.json` の unresolved 配列参照。

---

## 11. 開発スコープ・スケジュール（Phase 配分）

```
Phase 1（MVP・自社利用）= 30 Must
  期限: とにかく早く・楽な道に逃げず長期負債ゼロ
  ゴール: 自社 1 案件を End-to-End 完走

Phase 1.5（社内拡張）= 12 Should
  期限: Phase 1 動作確認後すぐ
  ゴール: 社内 / 業務委託 2-3 人で複数案件並走 + 部署リーダー AI

Phase 2（β 試用）= 6 Could (C-1〜C-5 + C-10)
  期限: Phase 1.5 安定後
  ゴール: 1-2 社の協力先で受託案件 + COO AI 完成

Phase 3（商用 SaaS）= 4 Could (C-6〜C-9)
  期限: β 評価通過後
  ゴール: 商用提供開始

Future（個人クローン化）= C-11
  別アプリとして切り出し
```

### 着手順序（推奨）
```
[最優先] M-1 Supabase 基盤
   ↓
M-2 既存スキル整理 / M-19 bootstrap 振り分け / M-4 階層
   ↓
M-3 AI 社員ハイブリッド + M-22 3 階層対応 / M-21 custom_permissions / M-23 プロフィール
   ↓
M-5 + M-5b 仕様書 + 画面モック / M-6 タスク分解 / M-25 EARS / M-15 HTML レポート
   ↓
M-7 多 view UI / M-8 フェーズ管理 / M-9 依存グラフ / M-24 グローバル検索
   ↓
M-10a MCP / M-10b ▶︎ / M-11 壁打ち / M-20 LLM 抽象化
   ↓
M-10c 並列 swarm / M-10d WebSocket UI
   ↓
M-12 赤線 / M-26 Constitution
   ↓
M-13 GitHub / M-14 Slack / M-16 Obsidian
   ↓
M-17 Langfuse / M-18 監査 + バックアップ
```

---

## 11.5 M-31 project_bootstrap_enforcement (2026-05-10 追加)

**目的**: Build-Factory が回す全案件に「機械的強制レイヤー」を自動展開し、品質を担保する。

### 背景
Build-Factory 本体の開発で整備した強制レイヤー (CLAUDE.md / HANDOVER.md / IMPLEMENTATION_PROTOCOL.md / lint-mock.sh / validate-tickets.py / .claude/settings.json / tickets.json メタ完備) を、各案件 (受託 EC #4 / 内製 SaaS #2 等) でも自動配置する。これにより案件ごとの品質を担保する。

### 受け入れ条件 (EARS)
- **UBIQUITOUS**: The system shall maintain a `templates/project-bootstrap/` skeleton with all enforcement-layer files (CLAUDE.md.j2, HANDOVER.md.j2, IMPLEMENTATION_PROTOCOL.md, lint-mock.sh, validate-tickets.py, settings.json).
- **EVENT**: When a new workspace is created via POST /api/workspaces, the system shall create a GitHub repo and populate it with the rendered template.
- **EVENT**: When `templates/CHANGELOG.md` is updated on main, the CI shall trigger a dry-run migrate against every active workspace and require masato approval before propagating.
- **STATE**: While a workspace is in `bootstrapping` state, the system shall refuse other operations until `ready`.
- **OPTIONAL**: Where `--all` is given to `build-factory project migrate`, the system shall sequentially migrate every workspace.
- **UNWANTED**: If a rendered file still contains `{{ }}` (unrendered placeholder), the system shall fail validation and shall not commit.
- **UNWANTED**: If the bootstrap fails midway, the system shall not leave a partial repo on GitHub; it shall mark `workspace.status='bootstrap_failed'` for retry.

### 関連
- ADR: `docs/decisions/ADR-009-project-bootstrap-enforcement.md`
- 機能: F-003 workspace_management
- タスク: T-BTSTRAP-01 〜 T-BTSTRAP-06 (6 件)
- テンプレ: `templates/project-bootstrap/`

---

## 12. 改訂履歴

- **v1.1**（2026-05-10）: M-31 project_bootstrap_enforcement 追加 (ADR-009)
- **v1.0**（2026-05-09）: ヒアリング v2.1 → 要件定義 v1 への正式昇格
- ヒアリング v2.1（2026-05-09）= requirements-definition STEP 1〜2 確定事項
- ヒアリング v2.0（2026-05-09）= hearing 4STEP 完了
- v1 PROJECT_BRIEF（2026-05-01）= 旧版・廃版

---

## 関連ファイル

- `requirements-v1.html` — クライアント提出用 HTML
- `requirements_internal.json` — 機能要件詳細（開発チーム向け）
- `requirements_decision_log.json` — 判断ログ + 未確認事項 + リサーチ
- `../../hearing/2026-05-09_re-hearing/` — ヒアリング v2.1（前提ドキュメント）

## 次のスキル

```
architecture-design  ← 次着手
  → tech-stack
  → functional-breakdown
  → feature-decomposition
  → task-decomposition
  → distributed-dev（Claude Code 実装パッケージ化）
```
