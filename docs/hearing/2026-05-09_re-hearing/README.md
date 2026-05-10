# 2026-05-09 再ヒアリング — Build-Factory v2

このフォルダは、2026-05-09 に実施した Build-Factory の **再ヒアリング**（コンセプトから根本再設計）の最終出力をまとめたものです。

> v1 PROJECT_BRIEF（2026-05-01）はコンセプト含めて白紙化し、ここから新しい仕様体系（v2）が始まります。

**現在のバージョン：v2.1**（2026-05-09 改訂・requirements-definition STEP 1〜2 の確定事項を反映）

**🆕 後続成果物**：requirements-definition の STEP 6 完了出力は `docs/requirements/2026-05-09_v1/` に保管されました（要件定義書 v1.0 確定）。

---

## ファイル一覧

| ファイル | 役割 | 想定読者 |
|---|---|---|
| **`hearing_summary.md`** | ヒアリングサマリー（Markdown） | PM / クライアント / 社内共有 |
| **`hearing_summary.html`** | ヒアリングサマリー（HTML 版・Tailwind + SVG 図解付き） | 同上（リッチに読みたい時） |
| **`project_brief.json`** | プロジェクト起点 構造化データ | 後続スキル（requirements-definition / architecture-design 等）への入力 |
| **`decision_log.json`** | 判断ログ + Web リサーチ findings + ヒアリングパターン | MCP 連携 / 案件 DB 蓄積 / 次回類似案件の高速化 |

---

## クイックビュー

### コンセプト（v2 確定）
> **企画から納品までの全工程を 1 環境で完璧に進めるプロジェクト管理 OS**

### 解決する核心課題（v2.1 で研ぎ澄まし）
> **AI 開発が流行する一方、管理 / 品質の不足で「漏れ」「使えないものになる」事故が頻発している。Build-Factory はこの管理・品質の壁を AI チームと管理盤の一体化で破壊する。**

### 本質的なゴール
1 人で **10 案件並走**しても破綻しない開発体制を作り、SaaS 商用化する。1 案件あたり **5 並列タスク**を回し続けるスループット。

### Phase 1 Must（29 項目・v2.1）
- M-1〜M-19（v2.0 から継続・基盤 + AI 社員統合 + 仕様書 HTML + タスク分解 + 多 view + フェーズ + 依存グラフ + MCP + ▶︎ + swarm + 壁打ち + 赤線 + GitHub + Slack + HTML レポート + Obsidian + Langfuse + 監査 + bootstrap 振分け）
- **M-20** LLM プロバイダー抽象化レイヤー（マルチプロバイダー切替・拡張容易）
- **M-21** ロール custom_permissions UI + monitor ロール
- **M-22** AI 社員 3 階層対応（DB schema + 組織図 UI 簡易版）+ 個人ナレッジ namespace
- **M-23** アカウント設定 / プロフィール画面
- **M-24** グローバル検索
- **M-25** EARS notation 標準（acceptance-criteria テンプレ）
- **M-26** Constitution（プロジェクト不変原則）= 赤線リストの拡張

### 主要な方針転換（v1 からの差分・再掲）
- **Onlook / Open Design 不採用** → 仕様書 → HTML/CSS で完璧再現 + GrapesJS GUI 編集
- **出力フォーマット = HTML + Markdown ハイブリッド**（HTML デフォルト）
- **タスク ▶︎ 再生 + 並列実行 + swarm view** を Phase 1 から実装
- **DB / 認証 = Supabase 全面採用**（SQLite から移行）
- **AI 社員 = BMAD + Anthropic Agent Teams + 既存 96 スキル ハイブリッド**
- **実装層 LLM = 各自 Claude Pro/Max プラン**（Build-Factory 側 API 課金最小）
- **デプロイ環境 = 連携アダプタ式**（Vercel / Netlify / Coolify / Cloud Run / 自前 SSH）
- **ナレッジ母艦 = Obsidian**

### v2.1 で追加 / 確定したもの（CHANGELOG）

| # | 確定事項 |
|---|---|
| ① | 目的を「AI 開発の管理・品質問題を解決する」方向に研ぎ澄ました |
| ② | ターゲットを **受託会社 / 中小企業の開発リーダー / 個人開発者・副業エンジニア** まで拡張 |
| ③ | P-1 高本まさと年齢を **27 歳** に訂正 |
| ④ | 並列セッション = **1 案件 5 並列タスク**（10 案件並走で理論最大 50 並列） |
| ⑤ | Token 上限はデフォルト無制限・admin が金額設定で上限化（80% 警告 / 95% fallback / 100% 停止） |
| ⑥ | チャット層 LLM = **マルチプロバイダー抽象化**（Claude / OpenAI / Gemini / 軽量 LLM / 拡張容易） |
| ⑦ | パフォーマンス目標を **時間ベース → 品質ベース**に振替（ヒアリング深掘り完了度・タスク独立性 90% 等） |
| ⑧ | ロール権限の **細粒度化**（クライアント以外も含む custom_permissions）+ **monitor** ロール追加（第 6 ロール） |
| ⑨ | AI 社員 **3 階層構造**（COO / 部署リーダー / メンバー）+ **個人クローン化**（将来別サービス） |
| ⑩ | EARS notation を acceptance-criteria 標準形式として採用（Kiro 流） |
| ⑪ | Constitution（プロジェクト不変原則）を赤線リストの拡張として採用（GitHub Spec Kit 流） |
| ⑫ | アカウント設定 / プロフィール → Phase 1 / グローバル検索 → Phase 1 / オンボーディング → Phase 1.5 / モバイル → Phase 3 |

---

## AI 社員階層構造（将来の理想形）

```
🏢 AI 組織図（Phase 配分）

           ┌──────────────────────┐
           │    COO AI（総括）      │  ← Phase 2
           └──────────┬───────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
   │開発部    │  │デザイン部│  │QA 部     │  │ナレッジ部│  ← Phase 1.5
   │リーダー  │  │リーダー  │  │リーダー  │  │リーダー  │
   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
        │             │             │             │
   ┌────┴────┐  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐
   │PM秘書    │  │brand-   │  │test-    │  │curator   │   ← Phase 1
   │arch     │  │voice    │  │verif    │  │keeper    │
   │senior   │  │design-md│  │e2e-test │  │analyst   │
   │reviewer │  │ui-mockup│  │         │  │          │
   └─────────┘  └─────────┘  └─────────┘  └─────────┘

       👤 各ユーザーには「個人クローン」が紐づく
       ・本人の判断履歴・会話・ナレッジを学習
       ・クローン化サービスは将来別アプリとして切り出し
       ・Phase 1 から学習素地（user_interaction_log）は記録開始
```

---

## ロール構成（v2.1 確定 6 ロール）

| ロール | 用途 | デフォルト権限 |
|---|---|---|
| `account_owner` | アカウント所有者 | 全権限（課金含む） |
| `workspace_admin` | workspace 管理者 | workspace 内ほぼ全権限 |
| `contributor` | 開発担当 | 編集 / 実行 / 承認 / 閲覧 |
| `viewer` | 閲覧者 | 閲覧のみ |
| `client` | クライアント招待ユーザ | 招待タブのみ閲覧 + コメント |
| `monitor` 🆕 | 監視担当（社内 / 業務委託） | 全閲覧 + 承認（PR / 赤線 / 納品） |

→ `custom_permissions JSON` で**全ロール**の個別 override 可能（クライアント以外も含む）

---

## 次のスキル進行順（推奨・現在進行中）

```
hearing（完了）✅
  ↓
requirements-definition  ← STEP 3 進行中
  ↓
architecture-design
  ↓
tech-stack
  ↓
functional-breakdown
  ↓
feature-decomposition
  ↓
task-decomposition
  ↓
distributed-dev（Claude Code への実装パッケージ化）
```

---

## 関連ファイル

- `../2026-05-01_hearing_log.md` — v1 ヒアリングログ（参考）
- `../../PROJECT_BRIEF.md` — v1 PROJECT_BRIEF（参考・白紙化済）
- `../../PROJECT_BRIEF.json` — v1 構造化版（参考）
- `../../../README.md` — リポジトリ README

---

## 編集ルール

このフォルダは **生きた仕様書**です。
- requirements-definition 以降の詳細仕様（STEP 6 出力時）は別フォルダ（`docs/requirements/2026-05-09_v2.1/` 等）に切り出されます
- このフォルダは「ヒアリング完了時点 + 直近の確定事項」のスナップショットを保持します
- 大幅な再設計時は新しい日付フォルダ（例：`2026-XX-XX_re-hearing/`）を切ってください

---

## 改訂履歴

| 版 | 日付 | 主な変更 |
|---|---|---|
| **v2.1** | 2026-05-09 | 上記 CHANGELOG ① 〜 ⑫（requirements-definition STEP 1〜2 の確定事項を反映） |
| v2.0 | 2026-05-09 | v1 を白紙化、コンセプトから再設計（hearing 4 STEP 完了） |
| v1.0 | 2026-05-01 | 初版 PROJECT_BRIEF 作成（Onlook 統合・並走前提） |
