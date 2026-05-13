# Build-Factory v2 ヒアリングサマリー（再ヒアリング）

**作成日**：2026-05-09
**改訂日**：2026-05-09（v2.1 — requirements-definition STEP 1〜2 の確定を反映）
**ヒアリング対象**：高本まさと（**27 歳** / `info@engine-base.com`）
**前回ブリーフ**：`docs/PROJECT_BRIEF.md`（v1, 2026-05-01）→ コンセプト含めて再定義
**ステータス**：hearing 4STEP 完了 → requirements-definition STEP 3 進行中

---

## プロジェクト概要

- **作るもの**：Build-Factory（開発工場 OS）
- **本質的なゴール**：ヒアリング → 要件定義 → 設計 → タスク分解 → 実装 → テスト → 進捗管理 → 納品 までを 1 つの Web アプリで完璧に進められる環境
- **本質的な動機**：1 人で 10 案件並走しても破綻しない開発体制を構築し、SaaS 商用化する

### 解決する核心課題（v2.1 で研ぎ澄まし）
> **AI 開発が流行する一方、管理 / 品質の不足で「漏れ」「使えないものになる」事故が頻発している。Build-Factory はこの管理・品質の壁を AI チームと管理盤の一体化で破壊する開発工場 OS。**

具体的に解決する 4 課題：
1. AI 出力に**漏れがあって完成品として使えない**（多層検証・リーダー壁打ちで解消）
2. AI に**管理が追いつかない**（フェーズ管理 + 依存グラフ + 影響分析で解消）
3. AI 開発の**品質が属人化**（HTML 仕様書 + acceptance-criteria + 評価基盤で標準化）
4. 案件横断・チーム横断で**ナレッジが流れる**（Obsidian 母艦 + 自動キュレーションで蓄積）

### コンセプトの再定義（v2）
v1 は「決めるのは人間 / AI が実行」を**コンセプト**にしていたが、これは**設計思想**に過ぎない。
コンセプト = **「企画から納品までの全工程を 1 環境で完璧に進めるプロジェクト管理 OS」**

---

## ターゲットユーザー（v2.1 で拡張）

| ペルソナ | 関与度 | 想定 |
|---|---|---|
| **P-1: 高本まさと**（自社・dogfood 主ユーザ）| 🔴 最高 | 27 歳 / 1 名運営代表 / 10 案件並走 |
| **P-2: 受託会社 PM / シニアエンジニア** | 🔴 高（Phase 2 主顧客） | 30〜40 代 / 案件 5〜10 並行 / 受託の収益性向上 |
| **P-3: 中小企業の開発リーダー** | 🔴 高（Phase 2 主顧客） | 30〜50 代 / 自社プロダクト開発 / メンバー 2〜10 人 / 属人化解消 |
| **P-4: 個人開発者 / 副業エンジニア** | 🟡 中（Phase 2） | 副業 + 本業並走 / Pro 1 契約で最大効率 / コストセンシティブ |
| **P-5: 監視担当**（社内 or 業務委託） | 🟡 中（内部ロール） | チェックだけで品質担保 / 異常検知 |
| **P-6: クライアント**（招待される側） | 🟡 中 | 進捗確認 / コメント反映 / IT リテラシー幅広い |

---

## 成功の定義

### 定量目標
- 自社 1 案件を Build-Factory + Claude Code で End-to-End 完走（要件投入 → 納品）
- 1 人で 10 案件を破綻なく並走（**1 案件あたり 5 並列タスク**）
- AI 出力差し戻し率 **80% → 20% 以下**
- 1 タスクあたり Token コストが workspace 上限内に収まる
- SaaS マルチテナント・認証・権限が商用提供レベル

### 定性目標 + 品質ベース KPI（v2.1 で追加）
- 「もう手放せない」と感じる
- 情報過多にならない（progressive disclosure / role-based view）
- 監視担当が「確認するだけで OK」と言える
- 短期に早く回り、長期で負債を残さない
- **ヒアリング深掘り KPI**：曖昧表現の検出 → 確認回数 / 暗黙前提の顕在化数
- **タスク分解 KPI**：単独実行成功率 **90% 以上** / 依存関係漏れ率 **5% 以下** / タスク粒度妥当率（1 タスク = 1 セッションで完了する率）
- **応答 KPI**：起動 → 最初の出力 **10 秒以内（中央値 5 秒）** / WebSocket レイテンシ **100ms 以内（中央値 50ms）**

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
| **法的要件** | 下請法（受託案件）/ NDA / 秘密保持義務 / 個人情報保護法（クライアント情報含む場合）|

---

## アーキテクチャ全体像（7 レイヤー）

```
┌─────────────────────────────────────────────────────────┐
│ 1. UI レイヤー                                            │
│    Next.js 15 + shadcn/ui + Recharts + React Flow         │
│    HTML/Markdown ハイブリッド出力 + GrapesJS embed        │
│    progressive disclosure / role-based view               │
├─────────────────────────────────────────────────────────┤
│ 2. AI 社員レイヤー（ハイブリッド・3 階層構造）              │
│    COO（P2） / 部署リーダー（P1.5） / メンバー（P1）         │
│    BMAD 12 ペルソナ + Anthropic Agent Teams + 既存 96 スキル│
│    + 個人クローン namespace（学習素地・将来別サービス）      │
├─────────────────────────────────────────────────────────┤
│ 3. プロジェクト管理レイヤー（独自 moat）                   │
│    フェーズ管理 / 依存グラフ / 影響分析 / 自動伝搬         │
│    多 view（カンバン / リスト / ガント / DAG / swarm）     │
├─────────────────────────────────────────────────────────┤
│ 4. 実装連携レイヤー                                        │
│    Claude Code（OAuth で各自プラン）+ MCP サーバー         │
│    Anthropic Agent Teams で Plan/Gen/Eval 分離             │
│    ▶︎ 再生 + 並列 swarm + Hermes 風 crash detection       │
│    1 案件 5 並列タスクで連続実行                            │
├─────────────────────────────────────────────────────────┤
│ 5. 連携レイヤー                                            │
│    Slack（双方向 + Claude Desktop MCP）/ GitHub /          │
│    Obsidian Headless Sync / デプロイ連携アダプタ           │
├─────────────────────────────────────────────────────────┤
│ 6. データ + 認証 + 観測 レイヤー                           │
│    Supabase（Postgres + Auth + RLS + Realtime + Storage）  │
│    Langfuse self-host（観測 + eval + バージョン管理）      │
│    OpenFGA（必要箇所の fine-grained 権限・Phase 2）        │
│    ロール 6 種 + custom_permissions JSON                  │
├─────────────────────────────────────────────────────────┤
│ 7. ナレッジ + LLM レイヤー                                 │
│    Obsidian 母艦 + Mem0 + 自動キュレーション               │
│    LLM 抽象化（LiteLLM 等）でマルチプロバイダー切替         │
│    実装 = 各自 Claude Pro/Max（OAuth）                     │
│    チャット = 自社 API or BYOK（Claude / OpenAI / Gemini）  │
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
  acceptance-criteria は EARS notation で記述（Kiro 流）
  ↓
プロジェクトを Phase 1 / 2 に分割（フェーズ管理 UI）
  Constitution（プロジェクト不変原則）も合意
  ↓
タスクカードの ▶︎ 再生ボタン → Build-Factory が Claude Code セッションを起動
  ・仕様書 + acceptance-criteria + 関連ナレッジを初期プロンプトに注入
  ・Anthropic Agent Teams（Planner / Generator / Evaluator）が回る
  ・WebSocket でライブログ表示
  ↓
複数タスク同時 ▶︎（1 案件 5 並列） / 完了次第 自動補充
  ・依存グラフを尊重（親が未完なら子は ready 待機）
  ・親完了で子が自動 ready 昇格（Hermes 親子昇格）
  ・swarm グリッド view で全セッション同時監視
  ・circuit breaker：N 回連続失敗で自動 block
  ↓
Evaluator PASS → リーダー AI へ → 全タスク完了 → 統合テスト
  ↓
GitHub PR + HTML レビュー資料 → まさとさん（または monitor ロール）承認 → 納品 HTML 生成
  ↓
Slack 完了通知
  ↓
ナレッジが Obsidian に蓄積（成功パターン / 差し戻し履歴 / 失敗）
個人クローン学習データ（user_interaction_log）も自動蓄積
```

---

## 優先機能 Must（Phase 1：29 項目・v2.1）

### 基盤・統合
| # | 要件 |
|---|---|
| M-1 | Supabase 基盤移行（SQLite → Postgres + Auth + RLS） |
| M-2 | 既存 96 スキル整理（使うものだけ残す）|
| M-3 | AI 社員ハイブリッド統合（BMAD 12 ペルソナ + Anthropic Agent Teams + 既存）|
| M-4 | account / workspace / workspace_members 階層 |
| M-19 | 既存 Build-Factory bootstrap の振り分け実行 |

### コア機能
| # | 要件 |
|---|---|
| M-5 | ヒアリング → 仕様書 HTML 出力パイプライン |
| M-6 | 機能・タスク分解 + acceptance-criteria（**EARS notation**）|
| M-7 | 多 view タスク管理（カンバン + リスト + 依存グラフ React Flow）|
| M-8 | プロジェクト・フェーズ管理基盤 |
| M-9 | 依存グラフ + 基本伝搬 |

### 実装連携・並列実行（▶︎）
| # | 要件 |
|---|---|
| M-10a | MCP サーバー（データ流通） |
| M-10b | Claude Code セッション・スポナー（▶︎ 再生）|
| M-10c | 並列セッション・マネージャ（**1 案件 5 並列** + 親子昇格 + circuit breaker）|
| M-10d | WebSocket セッション・ストリーミング UI（swarm グリッド）|
| M-11 | リーダー AI 壁打ちループ（Plan / Gen / Eval）|

### 安全・連携
| # | 要件 |
|---|---|
| M-12 | 赤線リスト + 自動停止（主要 5 項目）|
| M-13 | GitHub 連携（PR + HTML diff 注釈レビュー）|
| M-14 | Slack 通知（片方向：失敗 / 赤線 / 進捗）|
| M-15 | HTML レポート全種（仕様 / 進捗 / レビュー / 納品物）|
| M-16 | Obsidian ナレッジ母艦連携（最小：単方向 export）|

### 運用・観測
| # | 要件 |
|---|---|
| M-17 | Langfuse self-host（観測 + コスト把握）|
| M-18 | 監査ログ + バックアップ |

### v2.1 で追加
| # | 要件 | 追加理由 |
|---|---|---|
| **M-20** | LLM プロバイダー抽象化レイヤー（Claude / OpenAI / Gemini / 軽量 LLM 切替・拡張容易） | チャット層のマルチプロバイダー対応 + BYOK |
| **M-21** | ロール custom_permissions UI + monitor ロール（第 6 ロール）| 全ロールで権限細粒度化（クライアント以外も）|
| **M-22** | AI 社員 3 階層対応（DB schema + 組織図 UI 簡易版）+ 個人ナレッジ namespace | COO / 部署リーダー / メンバー + クローン化素地 |
| **M-23** | アカウント設定 / プロフィール画面 | SaaS 必須・暗黙ではなく明示要件化 |
| **M-24** | グローバル検索 | 10 案件並走で必須 |
| **M-25** | EARS notation 標準（acceptance-criteria テンプレ）| Kiro 流・後続スキルとの互換性 |
| **M-26** | Constitution（プロジェクト不変原則）= 赤線リストの拡張 | GitHub Spec Kit 流・全セッション共通の不変ルール |

---

## Should（Phase 1.5：12 項目・v2.1）

| # | 要件 |
|---|---|
| S-1 | クライアント / メンバー招待 + タブ ON/OFF |
| S-2 | Slack 双方向 + Claude Desktop MCP 連携 |
| S-3 | GrapesJS Studio SDK 統合（HTML/CSS GUI 編集） |
| S-4 | Obsidian Headless Sync 双方向 |
| S-5 | impact-analysis + task-propagation スキル（既存実装影響分析）|
| S-6 | BYOK 設定 UI |
| S-7 | AI モデル / プロンプトバージョン管理 |
| S-8 | 通知 / アラートフル（停滞・依存破綻含む）|
| S-9 | ナレッジ自動キュレーション |
| S-10 | crash detection / circuit breaker 完成 |
| **S-11** | **部署リーダー AI**（開発部 / デザイン部 / QA / ナレッジ部） |
| **S-12** | **オンボーディング / チュートリアル**（role 別フロー） |

## Could（Phase 2 / 3）

| # | 要件 | フェーズ |
|---|---|---|
| C-1 | OpenFGA 細粒度権限 | Phase 2 |
| C-2 | AI 評価基盤（壁打ち精度 eval） | Phase 2 |
| C-3 | デプロイ連携アダプタ（Vercel / Netlify / Coolify / Cloud Run / 自前 SSH） | Phase 2 |
| C-4 | テンプレート / Boilerplate | Phase 2 |
| C-5 | E2E Playwright MCP 統合 | Phase 2 |
| **C-10** | **COO AI（全部署統括）** | Phase 2 |
| C-6 | Stripe / Lemon Squeezy 課金 | Phase 3 |
| C-7 | SaaS マルチテナント本格化（SLA / 障害自動監視）| Phase 3 |
| C-8 | 多言語 UI / モバイル最適化 | Phase 3 |
| C-9 | テンプレート Marketplace（コミュニティ共有）| Phase 3+ |
| **C-11** | **個人クローン化サービス（別アプリとして切り出し）** | 将来 / 別アプリ |

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

## ロール構成（v2.1 確定 6 ロール + custom_permissions）

| ロール | スコープ | デフォルト権限 |
|---|---|---|
| `account_owner` | account 全体 | 全権限（課金含む） |
| `workspace_admin` | workspace 単位 | workspace 内ほぼ全権限 |
| `contributor` | workspace 単位 | 編集 + 実行 + 承認 + 閲覧 |
| `viewer` | workspace 単位 | 閲覧のみ |
| `client` | workspace 単位 + タブ ON/OFF | 招待タブのみ閲覧 + コメント |
| **`monitor` 🆕** | workspace 単位 | 全閲覧 + 承認（PR / 赤線 / 納品） |

→ `custom_permissions JSON` で**全ロール**の個別 override 可能。

### 主要 Permission キー
- 閲覧：`view_phase_X` / `view_tab_Y` / `view_other_workspaces`
- 編集：`edit_spec` / `edit_task` / `edit_dependency` / `edit_phase` / `edit_design_html`
- 実行：`run_session` / `run_parallel_swarm` / `kill_session`
- 承認：`approve_pr` / `approve_red_line` / `approve_delivery`
- 招待：`invite_member` / `invite_client` / `change_role`
- 管理：`manage_skills` / `manage_red_lines` / `manage_ai_employees` / `manage_phases`
- コスト：`view_costs` / `manage_billing` / `set_token_limits`
- データ：`export_data` / `view_audit_log` / `delete_workspace`
- AI 設定：`set_byok_keys` / `change_llm_provider` / `manage_prompts`

---

## AI 社員 3 階層構造（Phase 配分）

```
🏢 AI 組織図（Phase 配分）

           ┌──────────────────────┐
           │    COO AI（総括）      │  ← Phase 2（C-10）
           └──────────┬───────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
   開発部         デザイン部       QA 部         ナレッジ部     ← Phase 1.5（S-11）
   リーダー       リーダー         リーダー       リーダー
        │             │             │             │
   ┌────┴────┐  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐
   PM 秘書       brand-voice    test-verif     curator         ← Phase 1（M-3）
   architect     design-md      e2e-test       keeper            BMAD 12 ペルソナ
   senior eng    ui-mockup                     analyst           + 既存スキル
   reviewer
   QA
   docs

       👤 各ユーザに個人クローン namespace（M-22）
       ・user_interaction_log で判断・会話を蓄積
       ・将来クローン化サービス（C-11）の学習データに
```

### Phase 1 で組む「拡張可能な土台」

```sql
-- AI 社員に階層・クローン情報を持たせる
ai_employees
  id, name, persona, skills[],
  hierarchy_level     -- 'csuite' | 'lead' | 'member' | 'personal_clone'
  parent_employee_id  -- 上位 AI（部署リーダーや COO）への参照
  cloned_from_user_id -- このAI社員が誰かのクローンなら、その user_id
  department          -- 'executive' | 'engineering' | 'design' | 'qa' | 'knowledge' | etc

-- ユーザー単位のナレッジ・会話履歴を分離保管
user_knowledge_namespace
  user_id, namespace_id, scope ('private' | 'shared')

user_interaction_log
  user_id, action_type, context_snapshot, decision, reasoning, created_at
  -- ↑ クローン化の学習データ
```

---

## ステークホルダー

| 役割 | 関与度 | 期待 / 懸念 |
|---|---|---|
| **高本まさと**（最終決裁・主ユーザ・27 歳） | 🔴 最高 | 10 案件並走 / SaaS 商用化 / もう手放せない／自分のリソース詰まり |
| **受託会社 PM**（Phase 2 主顧客） | 🔴 高 | 案件横断管理・若手の品質底上げ / クライアント往復の時間溶け |
| **中小企業 開発リーダー**（Phase 2 主顧客） | 🔴 高 | 少人数で AI 最大活用 / リリース速度向上 / AI 開発の漏れ・属人化 |
| **個人開発者・副業エンジニア**（Phase 2） | 🟡 中 | BYOK で安く運用 / 1 人だと品質チェックが甘い |
| **監視担当**（社内 / 業務委託） | 🟡 中 | チェックだけで品質担保 / AI ミス見逃し責任 |
| **クライアント**（受託案件先） | 🟡 中 | 進捗が見える・コメント反映が早い / 内部 AI に任せて品質低下 |
| **SaaS 顧客**（将来） | 🟢 低 → 🔴 高 | 自社開発 OS として利用 / データ分離 / SLA / セキュリティ |
| **AI 社員**（実体は LLM + スキル） | 🔴 実行主体 | 自領域で漏れなく実行 / ハルシネーション |
| **Claude Code**（外部実装エンジン） | 🔴 実行 | 与えられた仕様で実装 / 仕様の曖昧さ |
| **OSS / SaaS 提供元** | 🟢 観察 | OSS のライセンス変更・メンテ停止・破壊的変更 |
| **company-dashboard** | 🟡 並走（当面切り離し） | UI 整理 / データ重複回避 |

---

## 主要決定（v2.0 + v2.1 = 31 項目）

### v2.0 確定（D-1〜D-20）

| # | 決定 | 理由 |
|---|---|---|
| D-1 | v1 PROJECT_BRIEF を白紙化、コンセプトを再定義 | 「人間 / AI 役割分担」は設計思想に過ぎない |
| D-2 | Onlook / Open Design 不採用 | 仕様書 → HTML/CSS で完璧再現 + GrapesJS 編集 |
| D-3 | 出力フォーマット = HTML + Markdown ハイブリッド（HTML デフォルト） | Anthropic 内主流に追随・情報密度・共有性 |
| D-4 | タスク ▶︎ 再生 + 並列実行 + swarm view | Hermes Specify + Vibeyard swarm を Web 化 |
| D-5 | 自作回避・OSS / SaaS / SDK 最大活用 | 開発スピード + 保守負担削減 |
| D-6 | 商用利用可ライセンスのみ採用 | SaaS 商用化前提 |
| D-7 | 実装層 LLM = 各自 Claude Pro/Max | コスト分散・SaaS 限界利益向上 |
| D-8 | チャット層 LLM = 自社 API + BYOK の 2 系統 | ユーザー柔軟性 |
| D-9 | ローカル LLM は SaaS 不提供（self-host のみ）| スコープ絞り込み |
| D-10 | 認証 = Supabase Auth | DB と統一・RLS で multi-tenant 強制 |
| D-11 | DB = Supabase Postgres（SQLite から移行） | SaaS 化に必要・RLS が moat |
| D-12 | AI 社員 = BMAD + Anthropic Agent Teams + 既存スキル ハイブリッド | 既存資産活用 + 公式パターン採用 |
| D-13 | デプロイ = 連携アダプタ式（複数選択可） | ユーザー自由度 |
| D-14 | ナレッジ = Obsidian 母艦 | まさとさん既存運用との統合 |
| D-15 | 観測 = Langfuse self-host | コスト最小・MIT |
| D-16 | プロジェクト・フェーズ管理 + 依存グラフ + 影響分析 = moat | Linear / Jira / Notion にない領域 |
| D-17 | 既存 bootstrap 流用、現デザイン感継続 | 短期速度・既存資産活用 |
| D-18 | company-dashboard 当面切り離し（将来追加可能性） | スコープ絞り込み |
| D-19 | クライアント招待 = Phase 1 から組み込む | 受託案件で外部見せ早期必要 |
| D-20 | Phase 1 Must = ▶︎ 再生 + swarm まで含む（後ろ倒さない）| 楽な道に逃げない |

### v2.1 で追加（D-21〜D-31）

| # | 決定 | 理由 |
|---|---|---|
| **D-21** | 目的を「AI 開発の管理・品質問題を解決する」方向に研ぎ澄ます | AI 開発が流行する一方、漏れ・使えないものになる事故が頻発しているのが本質課題 |
| **D-22** | ターゲットを受託会社 / 中小企業の開発リーダー / 個人・副業まで拡張 | SaaS 顧客像を明確化 |
| **D-23** | 並列セッション = 1 案件 5 並列タスク（10 案件並走で理論最大 50 並列） | プラン制約と効率のバランス |
| **D-24** | Token 上限デフォルト無制限・admin が金額設定で上限化（80%/95%/100% 階段）| 柔軟性 + 制御可能性 |
| **D-25** | チャット LLM はマルチプロバイダー抽象化（LiteLLM 等）・拡張容易 | Gemini 等の追加が容易な adapter 設計 |
| **D-26** | パフォーマンス目標を時間ベース → 品質ベースに振替 | 時間より深掘り完了度・タスク独立性が本質 |
| **D-27** | ロール権限の細粒度化（custom_permissions）+ monitor ロール追加（第 6） | クライアント以外の細粒度制御 + 監視担当ロール |
| **D-28** | AI 社員 3 階層構造（COO / 部署リーダー / メンバー）+ 個人クローン化（別サービス） | 将来 COO で回せるレベルへ向け、Phase 1 から土台 |
| **D-29** | EARS notation を acceptance-criteria 標準形式として採用 | Kiro 流・後続スキルと互換性高い |
| **D-30** | Constitution を赤線リストの拡張として採用 | GitHub Spec Kit 流・プロジェクト不変原則 |
| **D-31** | アカウント設定 / グローバル検索 → P1 / オンボーディング → P1.5 / モバイル → P3 | 業界標準パターンを取り込み |

---

## 未解決の不明点

| # | 不明点 | 重要度 | 解決先 |
|---|---|---|---|
| 1 | Phase 1 Must 29 項目の各タスク見積もり工数 | high | task-decomposition |
| 2 | BMAD のどの部分を取り込むか（fork / 思想 / 完全採用） | high | architecture-design |
| 3 | Anthropic Agent Teams の最新 API 仕様確認 | high | architecture-design |
| 4 | GrapesJS Studio SDK の商用ライセンス費用 | medium | tech-stack |
| 5 | Supabase 移行時の既存 SQLite データ取り扱い | high | architecture-design |
| 6 | リーダー AI 壁打ちの「3 ターン」の具体実装 | medium | feature-decomposition |
| 7 | 並列セッション数の現実的上限（プラン別実測） | medium | tech-stack |
| 8 | クライアント招待 UI のメール文面 / 招待 URL 設計 | low | feature-decomposition |
| 9 | Obsidian Headless Sync の Phase 1 での簡易代替（単方向）の実装 | medium | architecture-design |
| 10 | 削除する既存 router / service の最終リスト | high | feature-decomposition |
| 11 | LLM プロバイダー抽象化（LiteLLM / 自前 SDK / etc）の選定 | high | tech-stack |
| 12 | EARS notation の具体テンプレート設計 | medium | feature-decomposition |
| 13 | Constitution（不変原則）と赤線リストの統合方法 | medium | architecture-design |
| 14 | 部署リーダー AI / COO AI のスキル構成 | medium | feature-decomposition |
| 15 | 個人クローン化サービスの切り出しタイミング | low | （将来検討）|

---

## 次のアクション（推奨）

1. **requirements-definition** STEP 3〜6 で M-1〜M-26 を機能要件として詳細化（**進行中**）
2. **architecture-design** スキルで Supabase 移行 + AI 社員ハイブリッド統合 + 3 階層構造の技術設計
3. **tech-stack** スキルで OSS 候補の最終選定（BMAD / Anthropic Agent Teams / GrapesJS / LiteLLM 等）
4. **functional-breakdown** スキルで画面・機能・ロール権限・エンティティ草案
5. **feature-decomposition** + **task-decomposition** で Phase 1 を実装単位に分解
6. **distributed-dev** で各タスクを Claude Code が単独実装できるパッケージに

---

## 関連ファイル

- `hearing_summary.html`（HTML 版・SVG 図解付き）
- `project_brief.json`（後続スキル引き継ぎ用構造化データ）
- `decision_log.json`（判断ログ + Web リサーチ findings）
- `../../PROJECT_BRIEF.md`（v1, 2026-05-01・参照履歴）

---

## 改訂履歴

- **v2.1**（2026-05-09）: requirements-definition STEP 1〜2 の確定事項を反映（D-21〜D-31 / Must M-20〜M-26 / Should S-11〜S-12 / Could C-10〜C-11 / 6 ロール / AI 3 階層 / ターゲット拡張 / KPI 品質ベース）
- **v2.0**（2026-05-09）: v1 を白紙化、コンセプトから再設計（hearing 4STEP 完了）
- v1.0（2026-05-01）: 初版 PROJECT_BRIEF（参考・廃版）

---

## 2026-05-13 Addendum — ADR-012 関連 follow-up

本 hearing 完了後 (2026-05-13), masato から以下の追加方針が口頭で確認された:

- **Obsidian Vault は Claude / LLM が自動で read/write してよい** (人間の手動編集は必須でない / チャット経由の自動更新 OK).
- **provider 切替は障害時 fallback だけでなく任意切替も基本要件** (BYOK / workspace 設定 / per-session header / A/B test).
- **OSS / Claude SDK 公式機能が存在するなら自前実装より優先** (NIH 削減方針 = ADR-012 採用).

これらは hearing v2.1 の Must / Should リスト本文を改訂するのではなく, **ADR-012 でカバーされる方針**として記録する.

### 影響 ticket / spec
- T-AI-MEM-01〜04 (tickets.json 参照)
- T-024-04 (workspaces.preferred_provider migration)
- requirements-v1.md 2026-05-13 Addendum / architecture-v1.md / tech-stack-v1.md 同
