# Build-Factory v2.1 functional-breakdown v1（2026-05-09）

このフォルダは **functional-breakdown スキル STEP 3 の最終出力**を保管します。

> 要件定義 v1.0 + アーキ v1.0 → functional-breakdown v1.0 への昇格段階。次は feature-decomposition / tech-stack。

## ファイル一覧

| ファイル | 役割 | 想定読者 |
|---|---|---|
| **`functional-breakdown.html`** | ブログ記事風サマリー（HTML・全 4 セクション）| 全員 |
| **`screens.json`** | 43 画面の構造化データ | フロントエンド開発者 / API 設計入力 |
| **`features.json`** | 30 機能の happy path / error path / 通知 / 監査 | バックエンド開発者 / feature-decomposition 入力 |
| **`roles.json`** | 6 ロール + permission matrix + object constraints | 認可ライブラリ選定（tech-stack）|
| **`entities.json`** | 43 エンティティ + 関係 + インデックス | DB 設計確定 / ORM 選定 |

## クイックビュー

### 数字
- **画面**：43（仕様化 7 / 実行 6 / プロジェクト管理 4 / 認証 5 / アカ横断 6 / WS 横断 4 / レビュー 3 / AI 社員 3 / ナレッジ観測 3 / クライアント 2）
- **機能**：30（M-1〜M-26 + M-5b + M-10a/b/c/d）
- **ロール**：6（owner / ws_admin / contributor / viewer / client / monitor）
- **エンティティ**：43（要件定義の 30 → アーキ DB 設計で 42 → functional-breakdown で会話履歴 + テンプレ 3 つ追加）
- **タブ**：11（client は 5 タブのみ default visible）

### v1.0 で確定した主要決定（17 件）
1. R-002 / R-006 = **完全並列**（admin = 攻め / monitor = 守り）
2. **custom_permissions マトリクス** 30+ キー × 6 ロール 確定
3. client visible タブ = **5 default visible**（概要 / 仕様 / モック / 進捗 / レビュー）
4. 通知デフォルト = **即時** + カテゴリ × 個別 ON/OFF + メール（招待 + 重要 P1 / 通常 P1.5）
5. account_dashboard KPI = **Hero 4 + 主要 4 + サブ折りたたみ**（10 案件並走中核 UX）
6. cost_dashboard = **8 タブ**（日次 / 月次 / プロバイダー / モデル / ユーザ / WS / セッション / アラート）
7. swarm_grid = **16 デフォルト + 4/9/16/64 可変 + 仮想化**
8. GrapesJS（P1.5）= **MIT 版開始 + Studio SDK 評価後採用**（基本なんでも + AI 補助 + copy-as-prompt）
9. F-010c crash detection = **resume 機能正式採用**（4 択：resume / 再実行 / キャンセル / 手動修正）
10. ユーザ削除 cascade = **30 日 grace + GDPR 準拠 + audit_logs の user_id NULL 化**
11. workspace 削除 = **soft delete 90 日 + ナレッジ / Constitution は account 横断保管**
12. Constitution 改訂 = **動作中セッションは旧版で完了**・新版は新規セッションから
13. F-021 自分自身権限剥奪 = **他 admin 居なければ block**・owner は絶対 block
14. **E-041 ChatThread / E-042 ChatMessage** 新設（会話履歴 = user_interaction_log と別管理）
15. **E-043 Template** 新設（プロジェクト / フェーズ / タスク / AC / Constitution テンプレ）
16. NDA 機密 = **workspace 単位**（細粒度過ぎず・他ツール標準）
17. WorkspaceSetting JSONB = **8 セクション**（notification / llm / integration / ui / limits / safety / knowledge / confidential）

## 次のスキル進行順

```
✅ hearing v2.1
✅ requirements-definition v1.0
✅ architecture-design v1.0
✅ functional-breakdown v1.0  ← イマココ完了
  ↓
tech-stack（OSS 候補確定 + 並列 PoC + DPA + LiteLLM 詳細 + GrapesJS Studio SDK 採否）
  ↓
feature-decomposition（13 モジュール境界に従って機能を分散開発粒度に + 壁打ち 3 ターン具体実装）
  ↓
task-decomposition（Phase 1 Must 30 項目を実装単位に + 工数見積もり + EARS notation 紐付け）
  ↓
distributed-dev（Claude Code 実装パッケージ化 + dogfooding 開始）
```

## 関連ファイル
- `../../requirements/2026-05-09_v1/` — 要件定義 v1.0
- `../../architecture/2026-05-09_v1/` — アーキ設計 v1.0
- `../../hearing/2026-05-09_re-hearing/` — ヒアリング v2.1

## 改訂履歴
- **v1.0**（2026-05-09）：functional-breakdown 3 STEP 完了・4 JSON + HTML 出力
