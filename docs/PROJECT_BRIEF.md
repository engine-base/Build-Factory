# Build-Factory プロジェクトブリーフ

> このドキュメントは Build-Factory の**目的・ゴール・要件・制約・設計思想**を完全に引き継げる形でまとめたもの。新しいセッション・新しい担当者は **このファイルを最初に読むこと**。

---

## メタ情報

| 項目 | 内容 |
|---|---|
| プロジェクト名 | **Build-Factory** |
| リポジトリ | https://github.com/engine-base/Build-Factory |
| ローカル | `~/Documents/Build-Factory/` |
| ブランチ | `feature/dev-specialization` (開発中) / `main` |
| 親会社 | 株式会社 ENGINE BASE |
| 最終決裁者 | 高本まさと（masato）<info@engine-base.com> |
| ヒアリング日 | 2026-05-01 |
| ステータス | Bootstrap 完了 → 開発特化フェーズ着手 |

---

## 1. なぜこれを作るのか（背景）

### 業界課題（マクロ）

- 受託案件は増えているが**エンジニアが足りない**（採用も育成もコスト高）
- AI コーディング（Claude Code / Cursor / Devin）は**個人の道具**として強いが、**チーム型・長期プロジェクト型**の支援がない
- 既存ツール（Notion / Linear / Asana）は**管理盤**としては機能するが、**実装エンジンとの連動・AI による自律品質保証**は弱い
- Okta「Businesses at Work 2026」によれば、AI エージェントが「非人間アイデンティティ」として企業に増加（前年比 650%）。Notion も日本で 25% 増・初の TOP10 入り → **AI を社員として組織に組み込む流れは既に来ている**

### 個人課題（まさとさん）

- 1 人で複数案件を並行すると context switch コストが爆発
- 「AI に頼んでも 8 割は微妙な仕上がりで、自分で壁打ちして直す時間が結局必要」
- company-dashboard で会社運営の AI 社員フレームワークは作ったが、**開発業務専用版**がない
- SaaS として商用化できるレベルにしたい

### 既存ソリューションの限界

| ツール | 強み | 限界 |
|---|---|---|
| Claude Code / Cursor | 実装が速い | **個人**の道具・複数案件並行管理が弱い |
| Devin / Aider | 自律実装 | **品質保証が浅い**・人間判断が必要な瞬間の handoff が雑 |
| Notion AI | ドキュメント生成 | **実装連携なし**・MCP からのアクション起動が弱い |
| Linear / Jira | タスク管理 | **AI 統合が外付け**・仕様書工場ではない |
| GitHub Copilot | コード補完 | **個別ファイル単位**・全体設計はできない |

→ Build-Factory はこの**空白地帯**を埋めにいく。

---

## 2. 本質的なゴール

### 一言で言うと

**「決めるのは人間 / 準備・実行・管理・品質保証は AI チーム」を完璧に成立させる、開発工場 OS。**

### 役割分担（最重要・誤解されやすい）

```
┌─────────────────────────────────────────────────┐
│ 人間（まさとさん / 監視担当）                      │
│  ・何を作るかを決める                             │
│  ・要件・設計の最終判断                           │
│  ・インフラ・アカウント登録など物理タスク           │
│  ・赤線（重要判断）の承認                         │
│  ・クライアントとのリアルなやりとり                 │
└─────────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────────┐
│ AI 社員チーム（Build-Factory が組成）               │
│  ・決めるのを完璧に補助（要件捕捉・分解・案出し）    │
│  ・決まったことを完璧に実行（仕様書化・タスク分解）  │
│  ・全てを完璧に管理（タスク・進捗・成果物・履歴）    │
│  ・リーダー AI が下の社員出力を**壁打ち**して品質保証│
└─────────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────────┐
│ Claude Code（外部実装エンジン）                    │
│  ・MCP 経由で Build-Factory からタスク取得          │
│  ・実装・テスト・コミット・PR 作成                  │
│  ・成果物を Build-Factory へ書き戻し                │
└─────────────────────────────────────────────────┘
```

### moat の核心（これが Build-Factory の独自価値）

1. **リーダー AI による壁打ちループ**
   下位 AI の出力（仕様書・モック・PR）を**完璧になるまで差し戻す**仕組み。今までまさとさんが手動で行っていた品質保証の負担を肩代わりする。
2. **ナレッジで AI が育つ**
   過去の差し戻し履歴・監視担当の修正・クライアント評価が蓄積され、リーダー AI の指摘精度が時間と共に向上する。
3. **多層検証**（実装 AI → レビュー AI → QA AI → セキュリティ AI）
   ハルシネーション率を多層フィルタで下げる。
4. **管理盤と工場の一体化**
   Notion + Linear + Cursor が分断している領域を 1 つの OS にまとめる。

---

## 3. 成功の定義

### 定量目標

- **1 人で 10 プロジェクト並行**（破綻なく回る）
- **リーダー AI 壁打ちで下の AI 出力差し戻し率を 80% → 20% 以下**
- **自社で 1 案件完走**（最初の検証案件）
- 要件投入 → 仕様書完成リードタイム（要計測ベンチマーク策定）

### 定性目標

- まさとさんが「もう手放せない」と感じる
- 監視担当が「確認するだけで OK」と言える品質
- SaaS 顧客が「これがないと開発回らない」と感じる
- Notion AI / Linear / ClickUp / Devin がカバーしていない領域を埋める

---

## 4. プロダクト概要

### 全体構造

```
[Account] = 課金単位・AI 社員所有・ナレッジ所有
  ├─ Owner（作成者のみ・アカウント所有者）
  ├─ AI 社員チーム（account 共通・全 workspace で兼任）
  │    ・PM 秘書（要件捕捉・タスク分解・進行管理）
  │    ・アーキテクト（設計判断・技術選定・ADR）
  │    ・シニアエンジニア（実装方針・コード生成）
  │    ・レビュアー（PR レビュー・品質ゲート）
  │    ・QA（テスト戦略・E2E 設計）
  │    ・DevOps（CI/CD・デプロイ・運用監視）
  │    ・ドキュメント担当（README / ADR / changelog）
  ├─ ナレッジ（account 内で共有・機密ラベル付きは workspace 横断不可）
  └─ Workspaces[]
       ├─ Workspace = 1 プロジェクト
       ├─ Workspace Members（プロジェクト単位で招待・role 個別設定）
       │    ・admin / contributor / viewer / client（role はカスタマイズ可）
       └─ project data
            ・タスク・要件・仕様書・モック・PR・コメント・チェックリスト
            ・クライアントは特定 タブのみ閲覧可（タブ ON/OFF 切替）
```

### 2 階層ダッシュボード

```
[Account ダッシュボード] 全 workspace 俯瞰
  ・各 workspace の進捗・担当 AI・異常アラート
  ・コスト現状・Token 使用量
  ・Account メンバー一覧

[Workspace ダッシュボード] プロジェクト個別
  ・このプロジェクトのみの情報（他案件は一切見えない）
  ・タスク・要件書・モック・PR・コメント
  ・クライアントが見られる範囲はタブで制御
```

### 開発フロー（標準）

```
人間（まさとさん）が要件を初期投入
    ↓
[PM 秘書] hearing スキルで深掘り → 要件 artifact 生成
    ↓
[アーキテクト] architecture-design + tech-stack で設計
    ↓
[シニアエンジニア] feature-decomposition + task-decomposition でタスク分解
    ↓
各タスクに acceptance-criteria でチェックリスト紐付け
    ↓
[Claude Code] が MCP で bf_get_next_task → bf_get_spec で取得 → 実装・テスト
    ↓
[レビュアー AI] が PR を壁打ち → 差し戻し or OK
    ↓
[QA] verification-loop で最終確認
    ↓
[DevOps] release-planning で本番投入準備
    ↓
[ドキュメント担当] documentation で changelog 生成
    ↓
[PM 秘書] delivery で納品
```

各ステップで artifact が生まれ、次の AI に handoff される。

---

## 5. 機能要件

### Must（MVP に絶対必要）

| # | 要件 | 詳細 |
|---|---|---|
| M-1 | Account / Workspace 階層 | 課金単位 + プロジェクト分離 |
| M-2 | Workspace メンバー権限（configurable role） | 招待 + ロール変更 |
| M-3 | AI 社員 7 体（秘書 / アーキ / エンジニア / レビュー / QA / DevOps / Docs） | account 共通 |
| M-4 | 既存スキル流用（13 個） | hearing / requirements-definition / architecture-design / api-design / feature-decomposition / task-decomposition / acceptance-criteria / test-verification / decision-record / release-planning / delivery / verification-loop / skill-creator |
| M-5 | 要件 → 仕様書工場 | 人間擦り合わせ → Claude Code に渡せるレベルの仕様生成 |
| M-6 | タスク分解（機能/ページ/ブランチ単位） | 一気にやらない・繋げやすく |
| M-7 | チェックリスト | タスク単位 + 納品状態の 2 種 |
| M-8 | リーダー AI 壁打ちループ | moat 核心 |
| M-9 | MCP サーバー（Claude Code 連携） | bf_get_next_task / bf_get_spec / bf_load_skill / bf_post_progress / bf_attach_artifact / bf_request_review |
| M-10 | コメント機能（Figma/Notion 風 + AI 一括反映） | 要件・モックへ注釈 |
| M-11 | クライアント表示制御（タブ ON/OFF） | 同 workspace で見せる範囲切替 |
| M-12 | 技術スタック選定 AI（3 段階評価器 + Web 検索） | 過去案件 + 動向 + 制約 |
| M-13 | ナレッジ蓄積（成功 + 失敗 + ネガティブ + 機密ラベル） | account 横断・機密分離 |
| M-14 | 赤線リスト + 自動停止 | 後述「赤線リスト」7 項目 |
| M-15 | コスト管理（上限 + モデル切替 + API キー切替 + ローカル LLM） | workspace 単位設定 |
| M-16 | Account ダッシュボード | 全 workspace 俯瞰 |
| M-17 | Workspace ダッシュボード | プロジェクト個別 |
| M-18 | 既存 core 流用 | artifact / orchestrator / observability / slot tracking 全部 |

### Should（あると大幅に良くなる）

- S-1: 監査ログ・操作履歴（受託の説明責任用）
- S-2: 自動 Slack 通知（赤線抵触・人間判断必要・進捗報告）
- S-3: AI 評価基盤（壁打ち精度を eval で測定）
- S-4: バージョン管理 UI（仕様書・モック履歴）
- S-5: 進捗自動 rollup（Account レベル集約レポート）
- S-6: 新規スキル 4 つ
  - `client-comm-bridge`（まさとさん ↔ クライアントの会話を AI 秘書に同期）
  - `code-review-loop`（リーダー AI の壁打ちループ専用）
  - `claude-code-handoff`（Claude Code への仕様パッケージング）
  - `progress-rollup`（10 案件横断の進捗集約）
- S-7: クライアントコメントの自動分類（要件変更 / 質問 / 承認）

### Could（余裕があれば）

- C-1: 認証統合（Google SSO / GitHub OAuth）
- C-2: 課金（Stripe / Lemon Squeezy）
- C-3: 多言語対応（英語 UI）
- C-4: モバイル対応 UI（レスポンシブ強化）
- C-5: 通知設定の細分化（チャネル / 頻度）
- C-6: 障害時の人間エスカレーション自動化
- C-7: API 公開（外部システムから Build-Factory を叩く）

### Won't（今回はやらない・スコープ外）

| # | 除外内容 | 理由 |
|---|---|---|
| W-1 | AI 自身による要件発生 | 人間からの初期投入は必須・自動化は信用毀損リスク |
| W-2 | クライアント自身が UI を直接編集 | 権限管理が複雑化・誤操作リスク |
| W-3 | Build-Factory が直接本番デプロイ | 必ず人間承認を挟む |
| W-4 | Claude Code 以外の実装エンジン対応 | スコープ拡大・MVP 後検討 |
| W-5 | モバイルアプリ版 | Web 完結で十分 |
| W-6 | テンプレート機能（案件種別ごと） | 不要と判断 |
| W-7 | 案件 type の持ち方 | 削除（汎用設計で対応） |

---

## 6. 非機能要件

### パフォーマンス

- 10 workspace 同時並行で破綻しない
- LLM API 並列呼び出しでレート制限に引っかからない
- WebSocket でリアルタイム artifact 更新

### セキュリティ・データ分離

- account_id を全テーブルに必須化（マルチテナント）
- workspace_id でプロジェクト分離
- ナレッジの機密ラベル → workspace 横断時にフィルタ
- 顧客 API キー / 秘密情報の安全な保管（暗号化）
- 監査ログ（誰が何を承認・編集したか）

### コスト管理（重要）

- workspace 単位で月次・日次・1 タスク当たり Token 上限
- 超過時挙動: 警告 → 軽量モデル fallback → 停止 の段階制御
- API キー切替: 自社 API / 顧客持ち込み / ローカル LLM (Ollama)
- ダッシュボードでリアルタイム可視化

### 可用性

- Build-Factory が落ちても Claude Code 単独で開発継続可能
- 既存仕様書（artifact）は Markdown export 済の前提

---

## 7. 制約

| 制約 | 内容 | 影響 |
|---|---|---|
| 期限 | **なるべく早く**自社商用利用レベル / Phase 1 = 2〜3 週間目標 | MVP スコープ要絞り込み |
| 予算 | LLM API は Claude Code Pro 並みの上限想定 | モデル選定で工夫 |
| 技術スタック | company-dashboard と同じ基盤（Next.js 15 + FastAPI + SQLite） | 流用可能 |
| チーム規模 | 初期: まさとさん 1 人 / 中期: ENGINE BASE 内他スタッフ / 長期: SaaS 顧客 | ロールベース権限を最初から考慮 |
| 既存システム | company-dashboard と並走（独立稼働・干渉しない） | port 8001 / 3001 で分離 |

---

## 8. ステークホルダー

| 役割 | 関与度 | 期待 | 懸念 |
|---|---|---|---|
| まさとさん（最終決裁） | 🔴 最高 | 10 案件並行・SaaS 商用化 | 自分のリソースが詰まる事故 |
| 各プロジェクト監視担当 | 🟡 中 | チェックだけで品質担保 | AI のミスを見逃す責任 |
| クライアント（受託） | 🟡 中 | 進捗が見える・コメント反映が早い | 内部 AI に任せて品質低下 |
| AI 社員（7 体） | 🔴 実行主体 | 自領域で漏れなく実行 | LLM ハルシネーション |
| Claude Code（外部実装エンジン） | 🔴 実行 | 与えられた仕様で正確に実装 | 仕様書の曖昧さ |
| 将来の SaaS 顧客 | 🟢 低 (今) → 高 (将来) | 自社の開発 OS として利用 | データ分離・SLA |
| company-dashboard | 🟡 並走 | core を共有・干渉しない | 共有モジュール化の同期コスト |

---

## 9. データモデル（実装前提）

### 新規テーブル

```sql
-- 課金単位・AI 社員所有
accounts
  id, name, type (company/individual), plan, owner_user_id, created_at

-- アカウントメンバー（owner のみが基本だが将来拡張用）
account_members
  account_id, user_id, role (owner)

-- プロジェクト単位
workspaces
  id, account_id, name, project_meta JSON, created_at

-- ワークスペース毎にメンバー招待・ロール
workspace_members
  workspace_id, user_id, role (admin/contributor/viewer/client),
  custom_permissions JSON, created_at

-- 招待管理
workspace_invitations
  workspace_id, email, role, token, expires_at

-- 開発系特化（既に Build-Factory bootstrap で migration 済）
projects, repos, pull_requests, reviews, tasks, approval_queue
```

### 既存テーブルへの workspace_id / account_id 追加

```sql
ai_employee_config  → account_id 追加（workspace 横断で使える）
knowledge_base      → account_id + workspace_id（機密ラベルで分離）
threads             → workspace_id
artifacts           → workspace_id
conversation_log    → workspace_id
conversation_slots  → workspace_id
```

---

## 10. 連携先

### Claude Code（実装エンジン）

Build-Factory が **MCP サーバー**として公開：

```
bf_list_projects()              ワークスペース一覧
bf_set_active_project(id)       作業対象切替
bf_get_next_task()              次タスク取得
bf_get_spec(task_id)            仕様書 + 受け入れ基準 + 関連スキル
bf_load_skill(name)             SKILL.md 全文ロード
bf_post_progress(task_id, msg)  進捗書戻し
bf_attach_artifact(task_id, .)  生成物紐付け
bf_request_review(task_id)      レビュー AI に依頼
bf_get_review_feedback(id)      レビュー結果取得
```

### GitHub（ソースコード管理）

- gh CLI 経由（Issue / PR / Workflow / Code Review）
- `pull_requests` テーブルで PR 状態管理
- `reviews` テーブルで AI レビュー記録

### Slack（通知 + 承認）

- 赤線抵触時の人間承認依頼
- 進捗報告（バッチ）
- 監視担当への気づき push

### company-dashboard（姉妹プロジェクト）

- 完全独立稼働（DB / port / Slack token / Obsidian vault 別）
- 将来的に shared library 化検討（今は独立）

---

## 11. 赤線リスト（自動停止項目）

AI が以下のいずれかに該当する操作を試みた場合、**自動停止 + 人間承認待ち**：

| # | 領域 | 例 |
|---|---|---|
| 1 | 顧客 API キー / 秘密情報の漏洩 | env / コード / ログへの埋め込み |
| 2 | 本番 DB への破壊的書込み | DROP TABLE / DELETE 全件 |
| 3 | GitHub の force push / 他人ブランチ書換 | `git push --force` 等 |
| 4 | AI コール無限ループ（コスト爆発） | 上限超過時の自動停止 |
| 5 | メール / Slack の誤送信 | 承認なしの送信操作 |
| 6 | ナレッジ横断時の機密情報リーク | 顧客 A の話が顧客 B に出る |
| 7 | デプロイ判断の独断 | 本番デプロイは必ず人間承認 |

**カバレッジ問題への対応**:
- 必須通過: 80% 以上 → OK
- 推奨: 95%+
- 例外: E2E が物理的に書けない 3rd party UI は単体テストで代替可
- **「3 ターン連続で改善しない場合は人間エスカレーション」**ルールで無限ループ回避

---

## 12. ロードマップ

### Phase 1: MVP（自社内利用）= 2〜3 週間

```
スコープ:
  ・Account 1 つ + Workspace 3 並行
  ・AI 社員 7 体
  ・既存 13 スキル流用
  ・仕様書工場 + Claude Code MCP 連携
  ・タスク分解 + チェックリスト
  ・リーダー壁打ち（1 段階）
  ・ナレッジ蓄積（基本）
  ・赤線リスト主要 5 項目
  ・Account ダッシュボード簡易版

ゴール: 自社の 1 案件を Build-Factory + Claude Code で完走
```

### Phase 2: β（社外限定試用）= +3〜4 週間

```
追加:
  ・コスト管理強化
  ・権限細分化（custom role）
  ・コメント機能（Figma/Notion 風）
  ・AI 一括反映
  ・監査ログ
  ・Slack 通知
  ・赤線リスト 7 項目フル

ゴール: 1〜2 社の協力先で試用
```

### Phase 3: 商用 SaaS = +1〜2 ヶ月

```
追加:
  ・認証統合（Google SSO / GitHub OAuth）
  ・Stripe 課金
  ・マルチテナント本格化
  ・SLA 設計
  ・障害監視
  ・データバックアップ

ゴール: 商用提供開始
```

---

## 13. リスクと対応

| # | リスク | 影響 | 対応方針 |
|---|---|---|---|
| R-1 | LLM ハルシネーション | 仕様書信頼性 | リーダー壁打ち + 多層検証 + 監視担当チェック |
| R-2 | API コスト爆発（10 並列） | 経営インパクト | 上限管理 / 軽量モデル fallback / ローカル LLM 切替 / 顧客 API |
| R-3 | 機密情報の横断リーク | 信用毀損 | ナレッジ機密ラベル / 取得時フィルタ / 監査ログ |
| R-4 | Claude Code 連携の不安定さ | フロー停止 | MCP 標準準拠 / stub 実装 / フォールバック |
| R-5 | カバレッジ「終わらない」事故 | 案件停滞 | 「3 ターン改善なしで人間エスカレ」ルール |
| R-6 | 「思ってたと違う」仕様書 | 受託信頼ダメージ | hearing スキル徹底 + クライアントコメント + AI 秘書すり合わせ |
| R-7 | まさとさん 1 人で MVP 開発の負荷 | リリース遅延 | 既存 core 流用 / Phase 分割 / Claude Code 自体を実装エンジンに |
| R-8 | 赤線リスト抵触の見逃し | 重大事故 | ミドルウェア層で自動検出 + 違反時即停止 + 監査ログ |
| R-9 | SaaS マルチテナント設計ミス | 法的リスク | account_id 全テーブル必須 / クエリ層強制フィルタ / RLS 検討 |
| R-10 | Notion / Linear / Devin の追従 | 差別化喪失 | moat（壁打ち + ナレッジ + 多層検証）に集中 |

---

## 14. 既存資産の活用（重要）

### 流用するもの（company-dashboard から）

#### 既存スキル 13 個（dev フローカバー）
| スキル | 用途 |
|---|---|
| `hearing` | 要件捕捉 |
| `requirements-definition` | 要件定義 |
| `architecture-design` | アーキテクチャ設計 |
| `tech-stack` | 技術スタック選定 |
| `api-design` | API 設計 |
| `feature-decomposition` | 機能分解 |
| `task-decomposition` | タスク分解 |
| `acceptance-criteria` | 受け入れ基準 |
| `test-verification` | テスト戦略 |
| `decision-record` | ADR |
| `release-planning` | リリース計画 |
| `delivery` | 納品 |
| `verification-loop` | 検証ループ |
| `skill-creator` | 新スキル作成 |

#### 既存 core モジュール（fully copied）
- `services/artifact_service.py`（出力管理）
- `services/output_processor.py`（自動 view 生成）
- `services/orchestrator_graph.py`（LangGraph オーケストレーション）
- `services/slot_state.py` / `slot_extractor.py`（会話スロット）
- `services/skill_manager.py` / `skill_detector.py`（スキル管理）
- `services/observability.py`（Langfuse 連携）
- `services/long_term_memory.py`（Mem0 連携）
- `services/conversation_memory.py`（会話履歴・embedding）
- `ai_agents/secretary_agent.py`（AI 社員フレームワーク）
- `routers/artifacts.py`（artifact API + WebSocket）
- フロント: `components/artifacts/`（15 view）+ `components/chat/`

### 新規実装（Build-Factory 固有）

#### 新規スキル（4 個・Should レベル）
- `client-comm-bridge`
- `code-review-loop`
- `claude-code-handoff`
- `progress-rollup`

#### 新規テーブル
- accounts / account_members
- workspaces / workspace_members / workspace_invitations
- projects / repos / pull_requests / reviews / tasks（bootstrap で migration 済）

#### 新規 MCP ツール
- bf_get_next_task / bf_get_spec / bf_post_progress 等

#### 新規 UI
- 2 階層ダッシュボード（Account / Workspace）
- コメント注釈レイヤー（artifact 拡張）
- 赤線リスト承認 UI

---

## 15. 競合 / 業界トレンド

### 直接競合

| ツール | 強み | Build-Factory の差別化 |
|---|---|---|
| **Devin** | 自律実装 | チーム型（複数 AI 分業）+ 管理盤一体 |
| **Notion AI** | ドキュメント生成 | 実装連携（Claude Code MCP）+ 壁打ちループ |
| **Linear / Jira** | タスク管理成熟 | 仕様書工場 + AI による自律進行 |
| **Cursor / Claude Code** | 個人実装支援 | チーム化・複数案件並走・品質保証層 |

### 業界トレンド（参照: Okta Businesses at Work 2026）

- AI エージェントが「非人間アイデンティティ」として企業に増加（前年比 650%）
- Notion が日本で 25% 増・初の TOP10 入り（AI ワークスペースとして）
- セキュリティ・観測ツールが急成長（NinjaOne 240% / CrowdStrike 66%）

→ AI を社員として組織に組み込む流れは既に来ている。Build-Factory は**そのうち「開発」に特化した形**を取りに行く。

---

## 16. 引き継ぎ Quick Start

### 環境構築

```bash
cd ~/Documents/Build-Factory

# Backend
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env 設定（API キー）
cd ..
cp .env.example .env
# OPENAI_API_KEY / ANTHROPIC_API_KEY 等を編集

# 起動
cd backend
PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Frontend（別ターミナル）
cd ../frontend
pnpm install
pnpm dev -p 3001
```

### アクセス

- Dashboard: http://localhost:3001
- API Docs: http://localhost:8001/docs
- Langfuse（観測・任意）: http://localhost:3100

### 重要ファイル

- `docs/PROJECT_BRIEF.md` ← **このファイル**
- `docs/PROJECT_BRIEF.json` ← 構造化版（プログラム用）
- `docs/hearing/` ← ヒアリング詳細記録
- `README.md` ← 起動手順・技術スタック
- `backend/main.py` ← FastAPI エントリポイント
- `frontend/src/app/` ← Next.js ページ
- `data/db/build.db` ← SQLite DB

### company-dashboard との関係

- 完全独立稼働（DB / port / Slack token / Obsidian vault 別）
- 共有しているのは「コードベース上の core 概念」のみ（ファイルレベルでは独立コピー）
- 将来 shared library 化を検討（今はやらない）

### 現在のブランチ

- `main`: bootstrap 完了状態
- `feature/dev-specialization`: 開発特化フェーズ着手中（このブリーフ作成時点）

---

## 17. 決定ログ（何をなぜ決めたか）

| # | 決定 | 理由 | 代替案 | 不採用理由 |
|---|---|---|---|---|
| D-1 | company-dashboard を完全コピーして bootstrap | 動く土台を最速で確保 | 共通 lib 化から開始 | 抽出設計に時間がかかる |
| D-2 | Account → Workspace → Member 階層 | SaaS マルチテナント前提 | 単一テナント | 商用化を諦めることになる |
| D-3 | Members は workspace 単位 | 案件ごとに招待管理が現実的 | account 単位 | 受託案件で過剰権限になる |
| D-4 | テンプレート機能なし | 汎用設計で対応・スコープ削減 | 案件種別ごとテンプレ | スコープ拡大・複雑化 |
| D-5 | Claude Code は外部実装エンジン（MCP 連携） | 既存ツールの強みを活かす | 自社で実装 LLM 持つ | 開発工数・コスト過大 |
| D-6 | port 8001 / 3001 で company-dashboard と並走 | 干渉防止 | 同一 port で交互起動 | 開発時の切替コスト |
| D-7 | DB / Obsidian / credentials 等を完全分離 | データ事故防止 | 共有設定 | 顧客データ混入リスク |
| D-8 | 「3 ターン改善なしで人間エスカレ」ルール | カバレッジ無限ループ防止 | 100% 必須 | 実運用で停滞 |
| D-9 | リーダー AI 壁打ちループを moat とする | 他ツールが弱い領域 | 実装速度勝負 | Claude Code 等に勝てない |
| D-10 | ナレッジは社員別 + 共通の二段構成 | 既存 company-dashboard と同じ | 完全共通 / 完全分離 | 専門性 vs 汎用性のバランス |

---

## 18. 未解決事項（次の段階で詰める）

1. **MVP のリリース日**: 「なるべく早く」を具体日付に落とす
2. **monthly Token 上限の数値**: ¥◯万円 / 月で運用するか
3. **試運転対象案件**: どの案件で初めて回すか（汎用設計のため案件特定は後回し）
4. **チェックリストの粒度**: 1 タスクあたり何個入れるか（実装してから調整）
5. **リーダー AI の壁打ち回数上限**: 3 ターン？5 ターン？
6. **クライアント招待時のメール文面**
7. **Slack 通知の頻度・チャネル設計**
8. **Phase 1 の各機能の実装順序**（どれから着手するか）

---

## 19. 連絡先・参照

- 最終決裁: masato（info@engine-base.com）
- リポジトリ: https://github.com/engine-base/Build-Factory
- 姉妹プロジェクト: https://github.com/masato214/engine-base（company-dashboard）
- 参考記事: https://cloud.watch.impress.co.jp/docs/news/2105912.html
  → AI エージェントが企業に増加・Notion 急成長の業界トレンド

---

**このドキュメントは生きた仕様書です。決定が変わったら更新してください。**

*最終更新: 2026-05-01*
