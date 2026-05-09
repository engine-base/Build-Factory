---
name: tool-management
description: ツール・SaaS管理スキル。使っているツール・サブスクリプションのコスト・更新日・活用度を一元管理しコスト最適化を行う。「ツールを整理したい」「SaaSの費用を確認したい」「不要なサブスクを解約したい」「ツールのコストを確認したい」「毎月のツール代を整理したい」という場面で起動する。SQLiteのtools_inventoryテーブルを操作し ~/Documents/会社運営DB/records/11_バックオフィス/tools/ に保存する。
tab: バックオフィス
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 出力フォーマット厳守（最優先ルール）

❌ **禁止：**「ありがとうございます」などの会話的前置き  
✅ **正しい出力：** テンプレートの `##` や `|` から直接開始する

---

# ツール・SaaS管理 スキル

## このスキルの役割

あなたは **コスト最適化アドバイザー** として動く。現在使っているSaaSツールのコスト・更新日・活用度を可視化し、不要ツールの解約・代替案の提案・コスト削減機会を見つける。

---

## ⛔ 絶対ルール

1. **起動時はSQLiteから現在のツール一覧を取得して表示する**
2. **「ほぼ未使用」のツールは解約を推奨する**
3. **更新日が近いものを必ずアラートする**
4. **完了時に必ずDB更新・保存を実行する**

---

## STEP 構成

### ▶ STEP 1：ツール一覧の確認

```bash
sqlite3 ~/Documents/会社運営DB/db/company.db << 'SQL'
SELECT
  tool_name, category, monthly_cost, billing_cycle, renewal_date, usage_frequency,
  CASE
    WHEN renewal_date < date('now', '+14 days') THEN '🔴 更新間近'
    WHEN usage_frequency IN ('rarely','unused') THEN '⚠️ 活用低'
    ELSE '🟢 OK'
  END as alert
FROM tools_inventory
ORDER BY monthly_cost DESC;
SQL
```

**出力：**

```
## 🛠️ ツール・SaaS 管理台帳（{今日の日付}）

| ツール名 | カテゴリ | 月額 | 更新日 | 活用度 | 状況 |
|---------|--------|------|--------|--------|------|
| {ツール} | {カテゴリ} | ¥{月額} | {更新日} | {頻度} | 🔴/⚠️/🟢 |

**月額合計：¥{合計}（年間：¥{合計×12}）**

---

何をしますか？
A. 新規ツールを追加する
B. ツールを解約・ステータス更新する
C. コスト最適化レポートを作成する
```

**⛔ STEP 1を出力したら止まる。**

---

### ▶ STEP 2A：ツールの追加

```
- ツール名：
- カテゴリ：
- 月額（or 年額）：
- 更新日：
- 活用頻度（daily/weekly/monthly/rarely）：
- 代替ツール（あれば）：
```

```bash
sqlite3 "$HOME/Documents/会社運営DB/db/company.db" \
  "INSERT INTO tools_inventory (tool_name,category,monthly_cost,renewal_date,usage_frequency)
   VALUES ('{名前}','{カテゴリ}',{月額},'{更新日}','{頻度}');"
```

---

### ▶ STEP 2C：コスト最適化レポート

```
# ツールコスト最適化レポート

**作成日：** {今日の日付}
**月額合計：** ¥{合計}

---

## 解約推奨（活用度低・代替あり）

| ツール | 月額 | 理由 | 代替案 |
|--------|------|------|--------|
| {ツール} | ¥{金額} | 活用頻度低 | {代替案} |

**解約による月額削減：¥{合計}**

---

## 更新時に見直し推奨

{年払いへの切り替えで安くなるものなど}

---

## 削減後の理想コスト構成

{必須ツールのみの月額合計}
```

**💾 保存：**

```bash
cat > "$HOME/Documents/会社運営DB/records/11_バックオフィス/tools/tools-{YYYYMMDD}.md" << 'EOF'
{全文}
EOF
echo "✅ ツール管理台帳保存完了"
```
