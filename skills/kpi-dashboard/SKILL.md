---
name: kpi-dashboard
description: 経営ダッシュボード設計・更新スキル。会社の健康状態を一画面で把握できるダッシュボードを設計し、定期的に数値を更新する。「ダッシュボードを作りたい」「経営の数字を一覧で見たい」「KPIダッシュボードを更新したい」「会社の状態を確認したい」「今月の数字を整理したい」という場面で起動する。SQLiteの全テーブルを横断してサマリーを生成し ~/Documents/会社運営DB/records/05_経営戦略/kpi/ に保存する。
tab: 経営戦略
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 出力フォーマット厳守（最優先ルール）

❌ **禁止：**「ありがとうございます」などの会話的前置き  
✅ **正しい出力：** テンプレートの `##` や `|` から直接開始する

---

# 経営ダッシュボード設計・更新 スキル

## このスキルの役割

あなたは **経営アナリスト** として動く。SQLiteのすべてのテーブルを横断的に参照し、会社の「今の健康状態」をワンページのダッシュボードに集約する。週次・月次レビューのスタート画面として機能する。

---

## ⛔ 絶対ルール

1. **起動時は必ずSQLiteから最新データを取得する**（手入力に頼らない）
2. **週次モードと月次モードを使い分ける**
3. **「良い」「注意」「危険」の3段階で状態を色分けする**
4. **完了時に必ずファイル保存を実行する**

---

## STEP 構成

---

### ▶ STEP 1：モードの確認

```
## 📊 経営ダッシュボード

**A. 週次スナップショット（5分で確認）**
**B. 月次ダッシュボード（詳細版）**
**C. ダッシュボードの初期設計をする**
```

**⛔ STEP 1を出力したら止まる。**

---

### ▶ STEP 2A：週次スナップショット

**Bash toolで以下を一括実行してから出力する：**

```bash
sqlite3 ~/Documents/会社運営DB/db/company.db << 'SQL'
-- 未払い請求
SELECT '未払い請求', COUNT(*), SUM(total) FROM invoices WHERE status='unpaid';
-- 今月入金
SELECT '今月入金', COUNT(*), SUM(total) FROM invoices WHERE status='paid' AND strftime('%Y-%m',paid_date)=strftime('%Y-%m','now');
-- アクティブ案件
SELECT 'アクティブ案件', COUNT(*), SUM(amount) FROM pipeline WHERE stage NOT IN ('won','lost');
-- 今週タスク完了率
SELECT '今週完了率', AVG(completion_rate) FROM task_log WHERE task_date >= date('now','-7 days');
-- 要フォロー
SELECT '要フォロー', COUNT(*) FROM network WHERE last_contact < date('now','-90 days');
SQL
```

**取得データをもとに以下を出力する：**

```
## 📊 経営週次スナップショット（{今日の日付}）

┌──────────────────────────────────────┐
│ 💰 財務                               │
│  未払い請求：{N}件 ¥{合計}            │
│  今月入金済み：¥{合計}                │
│  手元資金（手動更新）：¥{金額}        │
├──────────────────────────────────────┤
│ 📈 営業パイプライン                   │
│  商談中：{N}件 ¥{見込み合計}          │
│  今月の受注見込み：¥{加重平均}        │
├──────────────────────────────────────┤
│ ✅ 実行力                             │
│  今週のタスク完了率：{%}             │
│  要フォローアップ：{N}名              │
├──────────────────────────────────────┤
│ 🚨 要対応                             │
│  {問題があれば赤字で表示}             │
└──────────────────────────────────────┘

### ⚠️ 今週注意すること
{異常値・期限超過・要対応事項}
```

---

### ▶ STEP 2B：月次ダッシュボード

**Bash toolで月次データを一括取得後：**

```bash
MONTH=$(date +%Y-%m)
sqlite3 ~/Documents/会社運営DB/db/company.db << SQL
SELECT '売上', SUM(total) FROM invoices WHERE status='paid' AND strftime('%Y-%m',paid_date)='$MONTH';
SELECT '経費', SUM(amount) FROM expenses WHERE strftime('%Y-%m',expense_date)='$MONTH';
SELECT '受注件数', COUNT(*), SUM(amount) FROM pipeline WHERE stage='won' AND strftime('%Y-%m',updated_at)='$MONTH';
SELECT '問い合わせ', COUNT(*) FROM outreach_log WHERE strftime('%Y-%m',contact_date)='$MONTH';
SELECT 'OKR進捗', AVG((kr1_current/kr1_target + kr2_current/kr2_target)/2) FROM okr WHERE status='active';
SQL
```

**月次ダッシュボードを出力：**

```
## 📊 {YYYY年MM月} 経営ダッシュボード

### 財務サマリー
| 指標 | 今月 | 先月 | 目標 | 状態 |
|------|------|------|------|------|
| 売上（入金済み） | ¥{金額} | ¥{金額} | ¥{目標} | 🟢/🟡/🔴 |
| 経費 | ¥{金額} | ¥{金額} | ¥{上限} | |
| 利益（概算） | ¥{金額} | ¥{金額} | ¥{目標} | |

### 営業サマリー
| 指標 | 今月 | 先月 | 目標 |
|------|------|------|------|
| 新規問い合わせ | {N} | {N} | {N} |
| 受注件数 | {N} | {N} | {N} |
| 受注金額 | ¥{金額} | ¥{金額} | ¥{目標} |
| パイプライン残高 | ¥{金額} | — | — |

### OKR進捗
| Objective | 進捗 | 状態 |
|----------|------|------|
| {OKR1} | {%} | 🟢/🟡/🔴 |
| {OKR2} | {%} | |

### 総評
{全体的な状態の2文サマリー}

### 今月のアクション優先順位
1. {最優先アクション}
2. {次のアクション}
3. {その次}
```

---

### ▶ STEP 2C：初期設計

**目標値・警告ラインの設定テンプレートを出力し、SQLiteにKPI定義を記録する。**

---

## 💾 出力ファイル保存（完了時に必ず実行）

`~/Documents/会社運営DB/records/05_経営戦略/kpi/DASHBOARD-{YYYYMMDD}.md`

```bash
cat > "$HOME/Documents/会社運営DB/records/05_経営戦略/kpi/DASHBOARD-{YYYYMMDD}.md" << 'EOF'
{ダッシュボード全文}
EOF
echo "✅ ダッシュボード保存完了"
```

```
---
✅ **ダッシュボード更新完了**
📄 ファイル：05_経営戦略/kpi/DASHBOARD-{YYYYMMDD}.md

次のステップ：
  週次 → weekly-review スキルと連携
  月次 → monthly-review スキルと連携
---
```
