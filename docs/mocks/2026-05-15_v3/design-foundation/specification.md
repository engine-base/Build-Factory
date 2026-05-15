# Build-Factory v3 デザイン基盤 仕様書

**作成日**: 2026-05-15
**プロジェクト**: Build-Factory (株式会社 ENGINE BASE)
**バージョン**: v3 (supersedes v1 `docs/mocks/2026-05-09_v1/design-tokens.md`)
**スキル**: design-foundation v1.0

---

## 1. ブランドコンセプト

| 項目 | 内容 |
|---|---|
| プロダクト | SaaS 型「開発工場 OS」 |
| ターゲット | 受託会社 / 中小企業の社内開発チーム / フリーランス PM |
| トーン | プロフェッショナル / 技術系 / 信頼感 |
| 参考系統 | **Linear 系** (高密度情報 + キーボード操作 + 控えめアクセント) |
| ブランドキーワード | 「開発の工場」「並列稼働」「松本の判断基準の再現」 |

## 2. カラーパレット

詳細は `tokens.json`。要約:

- **Base**: Slate (Gray 11 段階) + ENGINE BASE green (eb / 11 段階)
- **Semantic**: shadcn/ui HSL CSS 変数 (light + dark 両対応)
- **WCAG AA 厳守**: 全 critical text/bg pair で 4.5:1 以上
- **Sidebar**: 両 mode 共通の濃グリーン (eb-700 / eb-950) でブランド面積を維持

## 3. タイポグラフィ

- **Sans**: Noto Sans JP + Inter fallback
- **Mono**: JetBrains Mono
- **Body**: 14px / line-height 1.7 (日本語向け)
- **h1**: 24px (text-2xl) / **h2**: 18px (text-lg) / **h3**: 16px / **h4**: 14px
- **Micro**: 11px uppercase tracking-wider (label / meta)
- **KPI hero**: 28px mono tabular-nums

## 4. スペーシング・レイアウト

- **Sidebar**: 240px
- **Container max**: 1400px
- **Page padding**: 24px (px-6)
- **Card padding**: 20px (p-5)
- **Radius**: Modal 12px / Card 8px / Button 6px / Badge full
- **Breakpoint**: Desktop first (1280px+) / モバイル <640px は閲覧専用

## 5. コンポーネントルール

| Component | size | radius | 状態網羅 |
|---|---|---|---|
| Button | h-9 px-4 text-sm | rounded-md | 8 state 完備 |
| Input | h-9 px-3 text-sm | rounded-md | 5 state 完備 |
| Card | p-5 | rounded-lg | default + hover + selected |
| Modal | max-w-[480px] p-6 | rounded-xl | + drawer 右 |
| Badge / Tag | text-[11px] px-2 py-0.5 | rounded-full | 6 variant (success/warning/error/info/brand/default) |
| KPI Card | p-4 | rounded-lg | 4 variant (数値型/ゲージ/金額/アラート) |
| AI 社員 Chip | inline px-2 py-1 | rounded-md | Build-Factory 特化 |
| Status dot | w-1.5 h-1.5 + pulse | rounded-full | running / idle / paused / done |

## 6. UI ライブラリ・設定方針

- **shadcn/ui** (Tailwind v4 + HSL CSS 変数) を最優先
- **Lucide Icons** のみ / 絵文字禁止 (lint #1 で検出)
- **Mantine** は BlockNote 依存のみ許容
- **next/font/google** で fonts self-host
- **Recharts** チャート

## 7. 出力ファイル

| ファイル | 用途 |
|---|---|
| `specification.md` | この仕様書 (人間向け) |
| `tokens.json` | デザイントークン (コード連携) |
| `tailwind.config.js` | Tailwind 設定 (そのまま `frontend/` に統合可) |
| `globals.css` | CSS 変数定義 (Light + Dark) |
| `decision_log.json` | 11 個の判断記録 + research |

## 8. 実装統合手順

v3 mock 生成前に下記を `frontend/` に反映:

1. `frontend/tailwind.config.ts` を `tailwind.config.js` で上書き or merge
2. `frontend/src/app/globals.css` の `:root` と `.dark` を `globals.css` で置換
3. `frontend/package.json` に `tailwindcss-animate` 依存を追加
4. shadcn/ui コンポーネント (`components/ui/*`) は既存のまま使える
5. `frontend/src/app/layout.tsx` で `<html className={theme}>` で dark mode toggle 可能に

## 9. 既存実装との関係 (v1 → v3 migration)

- v1 design-tokens.md は freeze 扱い
- v3 では既存色値 (#1a6648) は維持
- 新規追加: 11 段階 scale / dark mode 変数 / shadcn HSL 統合 / WCAG AA 検証 / KPI Card / AI 社員 Chip 等の Build-Factory 特化 component

## 10. 次のステップ

1. PM レビュー (この仕様書) → 修正があれば反映
2. `frontend/` に反映 (上記 8 章手順)
3. **ui-mockup スキル**を起動 → 43 mock 生成 (S-001 から順次 PR)
