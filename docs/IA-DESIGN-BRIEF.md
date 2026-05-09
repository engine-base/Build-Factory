# Build-Factory Workspace IA デザインブリーフ
作成日: 2026-05-04
ヒアリング対象: 高本まさと (ENGINE BASE 代表)
担当: AI (本ヒアリングセッション)

## プロジェクト概要
- **作るもの**: Build-Factory の Workspace 内 IA (情報アーキテクチャ) — プロジェクト個別のサイドバー / 画面構成 / フェーズ制御
- **本質的なゴール**: 受託開発を AI 駆動 + 手動切替で「完璧に管理」できる OS。クライアント / 開発エンジニア / 管理メンバー の 3 者共有で、ヒアリングから納品まで全フェーズをカバーする。
- **成功の定義 (定量)**: PM が Workspace 入室から 3 クリック以内で「次やるべきこと」と「自分待ち項目」を把握できる。Claude Code MCP に bf_get_spec で完全な仕様 bundle を渡せる。
- **成功の定義 (定性)**: クライアントを招待しても迷わず承認・コメント・モック確認ができる。BF を使う PM は別 SaaS (Notion / Backlog / Linear) と併用する必要がない。

## 制約サマリー
- **期限**: 短期 MVP として直近で実装着手。各画面は段階的にリリース。
- **予算**: 内製、追加コストは BlockNote ライセンス (MIT 無償) のみ。
- **チーム**: 主に高本 + Claude Code (MCP)。
- **技術的制約**:
  - 既存 BF (Next.js 15 + FastAPI + Postgres/Supabase + Penpot iframe) を流用
  - Penpot は AGPL のため改変せず volume override + sub_filter のみ
  - 全 OSS は MIT / Apache / ISC 等の許諾的ライセンスのみ採用 (GPL/AGPL は不可、SaaS 商用前提)

## 確定事項

### 階層前提
| レベル | 内容 |
|---|---|
| アカウント | Workspaces一覧 / 秘書チャット (横断) / AI社員管理 / Artifacts ライブラリ / ナレッジ / スキル管理 / 実行ログ / 設定 |
| Workspace (プロジェクト) | プロジェクト管理系 + 開発フロー (AI 大分類) + 管理 (メンバー/共有/設定) |

→ **Artifacts・ナレッジ・実行ログ は Workspace に含めない**。プロジェクト固有の成果物は「進捗管理 + 各フェーズ画面」からアクセス。

### サイドバー構造 (3 セクション)
1. **プロジェクト管理** (6 項目)
   - ホーム / 進捗管理 / タスク管理 / スケジュール / 議事録 / アラート・質問
2. **開発フロー** (AI 大分類リーダー 7 体)
   - 秘書 AI / PM AI / 設計 AI / デザイナー AI / エンジニア AI / 品質 AI / DevOps AI
   - 各リーダーをクリック = アコーディオン展開 + 配下フェーズが見える
3. **管理** (3 項目)
   - メンバー / 権限 / 共有設定 / プロジェクト設定

### AI 大分類 7 体と担当スキル
| 大分類 | スキル束 |
|---|---|
| 秘書 AI | secretary (振分・全体ハブ) |
| PM AI | hearing / requirements-definition / proposal / estimate / product-strategy / acceptance-criteria / meeting-minutes |
| 設計 AI | architecture-design / tech-stack / api-design / feature-decomposition / task-decomposition |
| デザイナー AI | design-md / ui-mockup (+ Penpot 連携) |
| エンジニア AI | distributed-dev / integration |
| 品質 AI | test-verification / code-review / e2e-testing |
| DevOps AI | release-planning / delivery / operations / support-response / documentation |

### フェーズ依存 DAG + 制御モード
- **DAG**: ヒアリング → 要件 → [アーキ + デザイン + API + 提案] 並列 → 機能分解 → タスク分解 → 実装 → 統合 → テスト → レビュー → リリース → 運用
- **3 モード**: 厳格 / **ガイド (デフォルト)** / 自由
- **強行突破**: 理由入力必須、警告フラグ常時表示
- **完了判定**: AI 全 STEP 完了 + PM 承認 の併用
- **絶対飛ばせない**: ヒアリング / 要件定義 / 受入条件 / レビュー

### ロール別アクセス権限 (4 ロール)
- **admin**: 全権 (招待・編集・設定)
- **contributor**: 開発フロー全体・タスク管理・モック編集 (招待は不可)
- **viewer**: 全画面閲覧のみ
- **client**: ホーム (簡易) / 進捗閲覧 / 自分宛アラート / モックコメント / メンバー閲覧のみ

### デザイン基盤 — Calm Industrial
- 配合: SmartHR 70% + Linear 15% + esa 10% + Magic Moment 5%
- 詳細: [DESIGN-SYSTEM.md](./DESIGN-SYSTEM.md) (11 章)
- カラー: 白 + 薄グレー (#F5F7FA) + BF ブルー (#004CD9)
- フォント: Inter + Noto Sans JP
- アイコン: **Lucide のみ、絵文字一切禁止**
- 角丸: 4-8px、影なし、1px ボーダー区切り

### モック (11 画面) — 確定済み
- 場所: `frontend/public/mock/*.html`
- 共通 CSS: `_shared.css`、共通 partials: `_partials.js`
- インデックス: `index.html` から全画面に遷移可能
- 全ページ `file://` 動作確認済み

## OSS 採用方針
| OSS | 用途 | 採否 |
|---|---|---|
| **BlockNote** (MIT) | 議事録 / 要件定義 / 仕様書のリッチエディタ (Notion 風) | **採用確定** |
| shadcn/ui (MIT) | コンポーネント基盤 | 既存採用継続 |
| Lucide (ISC) | アイコン | 既存採用継続 |
| TanStack Query/Table (MIT) | データフェッチ・テーブル | 既存採用継続 |
| cmdk (MIT) | コマンドパレット (Cmd+K) | 必要時導入 |
| @dnd-kit (MIT) | Kanban ドラッグ強化 | 余裕があれば導入 |
| React Flow / xyflow (MIT) | DAG ビジュアル (進捗管理画面) | 進捗画面実装時に導入 |
| frappe-gantt (MIT) | ガントチャート | 必要時導入 |

→ **OSS はロジック・パターン参考が主**、まるごと採用は BlockNote のみ。

## 実装優先順位 (Must)
1. **CSS トークン適用** — `globals.css` に Calm Industrial トークン統合
2. **WorkspaceShell コンポーネント** — Sidebar + Header の共通シェル
3. **Workspace ホーム画面** — コックピット (DAG 進捗 + 次のアクション + 自分待ち + KPI)
4. **進捗管理画面** — DAG ビジュアル + ガント
5. **タスク管理画面** — 既実装の Kanban を新シェル / 新スタイルに統合
6. **AI 大分類 (PM ライン代表)** — リーダーチャット + フェーズ別作業エリア
7. **議事録画面 (BlockNote 導入)** — Notion 風エディタ
8. **メンバー / 設定 / アラート / スケジュール / 新規 / クライアントホーム**

## ステークホルダー
| 役割 | 関与度 | 期待・懸念 |
|---|---|---|
| 高本まさと (admin) | high | プロジェクト全権・最終決裁・クライアント窓口 |
| 開発エンジニア (contributor) | medium | 実装担当・タスク受領・コードレビュー |
| クライアント (client) | medium | 進捗確認・承認・モックコメント・質問回答 |
| AI 社員 7 体 | high (常時稼働) | 各フェーズの自走・成果物生成・PM へのレポート |

## 未解決の不明点 (後続フェーズで確認)
| 項目 | 重要度 | 解決先 |
|---|---|---|
| デザイナー AI の Penpot 自動操作 (モック自動生成) の API 範囲 | high | architecture-design |
| 共有リンク発行のセキュリティ要件 (期限 / 認証) | medium | requirements-definition |
| BlockNote のドキュメント永続化方式 (DB スキーマ / S3) | high | architecture-design |
| AI 社員 LLM モデル選定 (秘書 = Opus? Sonnet?) のコスト見積 | medium | tech-stack |
| アカウント横断 ナレッジの構造とプロジェクト固有ナレッジの境界 | medium | requirements-definition |

## リスク
| リスク | 影響度 | 発生確率 | 対応 |
|---|---|---|---|
| BlockNote のドキュメント永続化を作り込む工数 | high | high | 最初は localStorage / JSON ファイル保存で MVP、後で DB 化 |
| 11 画面を一気に実装すると工数オーバー | high | high | ホーム + 進捗 + タスク を最初に固める、他は段階的 |
| 既存 BF の `/workspaces/[id]/page.tsx` のタブを置換する破壊的変更 | medium | high | 旧ページをバックアップ、新シェルを別ルートで先行 |
| クライアント (client) ロール用の限定サイドバー / 権限制御の漏れ | medium | medium | 実装時にロールベース表示の検証ケースを書く |

## 次フェーズへの引き継ぎ
- **次に進む先**: 実装フェーズ (architecture-design / task-decomposition は省略、モック確定済のため直接コーディング)
- **入力**: 本ブリーフ + DESIGN-SYSTEM.md + frontend/public/mock 全 11 画面
