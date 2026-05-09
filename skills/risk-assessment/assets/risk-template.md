# リスク評価レポート - {{PROJECT_NAME}}

**評価日:** {{ASSESSMENT_DATE}}
**評価者:** {{ASSESSOR}}
**プロジェクト期間:** {{START_DATE}} 〜 {{END_DATE}}

---

## リスクサマリー

| レベル | 件数 | 対応方針 |
|--------|------|---------|
| 🔴 RED（Critical） | {{RED_COUNT}}件 | 即時対応・軽減策実施 |
| 🟡 YELLOW（Warning） | {{YELLOW_COUNT}}件 | 監視・Contingency Plan準備 |
| 🟢 GREEN（Monitor） | {{GREEN_COUNT}}件 | 定期監視・記録 |
| **合計** | **{{TOTAL_COUNT}}件** | |

---

## リスクマトリクス

| ID | リスク | カテゴリ | 影響度 | 確率 | 優先度 | 対策 | 担当 |
|----|--------|----------|--------|------|--------|------|------|
{{RISK_ROWS}}

---

## 即時対応が必要なリスク（RED）

{{HIGH_RISKS}}

---

## 監視が必要なリスク（YELLOW）

{{MED_RISKS}}

---

## 定期監視リスク（GREEN）

{{LOW_RISKS}}

---

## 最優先対応アクション

| # | リスクID | アクション | 担当 | 期限 | 完了基準 |
|---|---------|-----------|------|------|---------|
{{ACTION_ROWS}}

---

## 次回レビュー予定

- 次回リスクレビュー日: {{NEXT_REVIEW_DATE}}
- レビュー頻度: {{REVIEW_FREQUENCY}}
- レビュー担当: {{REVIEW_OWNER}}

---

*作成日: {{ASSESSMENT_DATE}} / 作成者: {{ASSESSOR}}*
