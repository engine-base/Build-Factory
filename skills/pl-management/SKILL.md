---
name: pl-management
description: 損益管理（P&L）スキル。売上・原価・経費を集計し月次・四半期・年次の損益計算書を自動生成する。「P&Lを作りたい」「損益を確認したい」「今月の利益を計算したい」「損益計算書を作りたい」「収益性を確認したい」という場面で起動する。SQLiteのinvoices・expensesテーブルからデータを取得し ~/Documents/会社運営DB/records/03_財務/pl/ に保存する。
tab: 財務・経理
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 出力フォーマット厳守（最優先ルール）

❌ **禁止：**「ありがとうございます」などの会話的前置き  
✅ **正しい出力：** テンプレートの `##` や `|` から直接開始する

---

# 損益管理（P&L） スキル

## このスキルの役割

あなたは **CFO** として動く。SQLiteのinvoices（売上）とexpenses（経費）テーブルからデータを自動取得し、損益計算書（P&L）を生成して収益性を分析する。

---

## ⛔ 絶対ルール

1. **まずSQLiteから自動取得する**（手入力不要）
2. **売上総利益・営業利益・純利益を区別して表示する**
3. **前月比・目標比を必ず出す**
4. **完了時に必ずファイル保存とDB記録を実行する**

---

## STEP 構成

### ▶ STEP 1：対象期間の確認

```
## 📋 P&L生成

対象期間を教えてください：
**A. 今月（{YYYY-MM}）**
**B. 先月（{YYYY-MM}）**
**C. 特定の月（YYYY-MM形式で入力）**
**D. 四半期（Q{N} YYYY）**

また、以下を補足してください：
- 月の目標売上（あれば）：      円
- 外注費（今月のSQLiteに未登録分）：      円
```

**⛔ STEP 1を出力したら止まる。**

---

### ▶ STEP 2：DBから自動取得 + P&L生成 + 保存

**Bash toolで以下を実行：**

```bash
MONTH="{対象月 YYYY-MM}"
sqlite3 ~/Documents/会社運営DB/db/company.db << SQL
-- 売上（入金済み）
SELECT '売上', SUM(total), SUM(subtotal), SUM(tax)
FROM invoices WHERE status='paid' AND strftime('%Y-%m',paid_date)='$MONTH';

-- 経費（科目別）
SELECT account_category, SUM(amount)
FROM expenses WHERE strftime('%Y-%m',expense_date)='$MONTH'
GROUP BY account_category;

-- 外注費
SELECT '外注費計', SUM(amount)
FROM expenses WHERE account_category='外注費' AND strftime('%Y-%m',expense_date)='$MONTH';
SQL
```

**取得データをもとに出力：**

```
# 損益計算書（P&L）

**対象期間：** {YYYY年MM月}
**作成日：** {今日の日付}

---

## 収益

| 項目 | 金額 |
|------|------|
| 売上高（税込） | ¥{売上計} |
| 消費税 | - ¥{消費税} |
| **売上高（税抜）** | **¥{税抜売上}** |

---

## 売上原価

| 項目 | 金額 |
|------|------|
| 外注費 | ¥{外注費} |
| **売上原価 計** | **¥{原価合計}** |

**売上総利益（粗利）：¥{売上-原価}（粗利率 {%}%）**

---

## 販売費・一般管理費

| 勘定科目 | 金額 |
|---------|------|
| 通信費 | ¥{金額} |
| 消耗品費 | ¥{金額} |
| 地代家賃 | ¥{金額} |
| その他 | ¥{金額} |
| **経費 計** | **¥{経費合計}** |

---

## 利益サマリー

| 指標 | 金額 | 率 | 前月比 |
|------|------|-----|--------|
| 売上総利益（粗利） | ¥{粗利} | {%}% | {+/-} |
| **営業利益** | **¥{営業利益}** | **{%}%** | {+/-} |
| 目標との差 | ¥{差} | — | — |

---

## 分析・コメント

**収益性評価：** {良好 / 注意 / 要改善}
{2〜3文の分析コメント}

**来月への示唆：**
{来月のアクション提案}
```

**💾 保存：**

```bash
cat > "$HOME/Documents/会社運営DB/records/03_財務/pl/{YYYY-MM}-pl.md" << 'EOF'
{全文}
EOF

sqlite3 "$HOME/Documents/会社運営DB/db/company.db" \
  "INSERT OR REPLACE INTO pl_records (month, revenue, operating_expenses, operating_profit, md_path)
   VALUES ('{YYYY-MM}', {売上}, {経費}, {営業利益}, '{path}');"
echo "✅ P&L保存完了"
```

```
---
✅ **P&L完成**
📄 ファイル：03_財務/pl/{YYYY-MM}-pl.md
🗄️ DB：pl_records に記録

キャッシュフロー確認は cashflow-forecast スキルを使用してください。
---
```
