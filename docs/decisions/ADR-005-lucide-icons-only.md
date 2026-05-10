# ADR-005: アイコンは Lucide のみ (絵文字禁止)

- **Status**: Accepted
- **Date**: 2026-05-09 (改めて 2026-05-10 に再確認)
- **Deciders**: 高本まさと

## Context

UI のアイコン表現について、初期モック作成時に複数の方式が混在した:

- 絵文字 (🔍 / 📄 / ▶︎ / ⚠ など)
- Lucide Icons (`<i data-lucide>`)
- Heroicons / Phosphor 等

混在の問題:
- **OS / フォント / ブラウザ依存** で絵文字レンダリングがバラバラ
- **アクセシビリティ** : 絵文字は読み上げソフトで意図と異なる名前になる
- **デザインシステム統一性** : 視覚スタイルが揃わない
- **macOS 絵文字 (`▶︎`) は Windows で表示崩れ**

## Decision

**Lucide Icons のみ使用** (絵文字は完全禁止) を方針とする。

### 適用範囲 (2026-05-10 amendment)

本ルールは **Build-Factory 自身の UI / 内部ログ / コメント** に適用する。
以下は **適用範囲外** (絵文字使用可):

| 適用範囲外 | 理由 | 対象ファイル例 |
|---|---|---|
| Slack / Chatwork など外部チャットへ送信するメッセージペイロード | 受信側 UI が Lucide をレンダリングできず、絵文字は IM の標準的な表現方法 | `backend/integrations/slack_block_kit.py` / `slack_client.py` / `chatwork_client.py` |
| ユーザー入力データ (チャットメッセージ・コメント等) | エンドユーザーが入力した絵文字は保持 | DB レコード / chat_messages.content |
| 外部 webhook ペイロード | 外部システム仕様で絵文字が必要な場合 | (該当なし) |

`scripts/lint-mock.sh --emoji` は上記適用範囲外ファイルを `EMOJI_EXEMPT_FILES`
で除外する。新規ファイルを除外したい場合は ADR-005 への追記 + lint-mock.sh の
allowlist 更新の 2 か所を必ず変更する。

### 採用理由
- **ISC License** (MIT 互換) で完全 OSS
- **1300+ アイコン** で実用上ほぼ全カバー
- **CDN 経由で利用可** (`unpkg.com/lucide@latest`)
- **shadcn/ui のデフォルトアイコン** として既に統合
- **stroke 系のクリーンなデザイン** が ENGINE BASE green と相性良し

### 実装ルール
```html
<!-- HTML の <head> -->
<script src="https://unpkg.com/lucide@latest"></script>

<!-- 使い方 -->
<i data-lucide="play" class="w-3.5 h-3.5 inline"></i>

<!-- 必ず </body> 直前で -->
<script>lucide.createIcons();</script>
```

### サイズ規約
- インライン (text 内): `w-3 h-3` または `w-3.5 h-3.5`
- ボタン内: `w-4 h-4`
- ヘッダー / 大型 UI: `w-5 h-5` 以上

### よく使うアイコン
- ナビ: `arrow-left`, `chevron-right`, `chevron-down`
- 状態: `check`, `x`, `alert-triangle`, `check-circle-2`
- アクション: `play`, `pause`, `pencil`, `trash-2`, `download`
- AI / システム: `bot`, `sparkles`, `boxes` (swarm), `zap`
- Web: `search`, `bell`, `settings`, `external-link`
- 編集: `pencil`, `code-2`, `palette`, `eye`
- Git: `git-branch`, `git-pull-request`, `git-compare`

詳細は `docs/mocks/2026-05-09_v1/design-tokens.md` §8。

## Consequences

### 得られるもの
- ✅ 全モック / 実装で視覚スタイル統一
- ✅ アクセシビリティ (aria-label 付与可)
- ✅ ライセンス問題なし (ISC)
- ✅ shadcn/ui との自然な統合

### 諦めるもの
- ❌ 絵文字 (🎉 など祝祭感) → 必要なら Lucide の `party-popper` で代替
- ❌ JS 必須 (`lucide.createIcons()` 実行が必要)
  - → SSR 時は React 版 `lucide-react` を使う

### 違反検知
- ESLint rule (実装フェーズで導入予定): プロジェクト内の絵文字を検出して警告
- モック生成時の自動 lint (T-S3-XX で実装)

### 関連
- 影響を受けるタスク: T-005b-03 (component_catalog) / 全 UI 実装タスク
- 違反履歴: 2026-05-10 に過去モック 175 箇所の絵文字を一括置換 (commit `23befe4`)
- 2026-05-10 追加: bootstrap 残存 223 件を解消 (frontend Lucide 化 / Slack 外部チャット例外化 / backend log テキスト化)
