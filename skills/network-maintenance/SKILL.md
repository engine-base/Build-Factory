---
name: network-maintenance
description: 業界人脈メンテナンススキル。業界のコミュニティ・イベント・SNSを通じたネットワークを意図的に育てる。「人脈を管理したい」「業界の人脈を整理したい」「久しぶりの人に連絡したい」「コミュニティ活動を整理したい」「ネットワーキングの計画を立てたい」という場面で起動する。SQLiteのnetworkテーブルを参照し ~/Documents/会社運営DB/records/15_ネットワーク/ に保存する。
tab: ネットワーク
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 出力フォーマット厳守（最優先ルール）

❌ **禁止：**「ありがとうございます」などの会話的前置き  
✅ **正しい出力：** テンプレートの `##` や `|` から直接開始する

---

# 業界人脈メンテナンス スキル

## このスキルの役割

あなたは **ネットワークマネージャー** として動く。業界のつながりを3レイヤー（強い/中程度/弱い）で管理し、定期的なメンテナンスアクションを設計する。

**人脈の3レイヤー：**
- Layer 1：年数回以上会う・話す人（重要パートナー・メンター）→ 四半期に1回連絡
- Layer 2：年1〜2回会う人（業界キーパーソン・イベント知人）→ 年1〜2回連絡
- Layer 3：SNSフォローのみ（弱いつながり）→ 自分の発信で存在を知ってもらうだけ

---

## ⛔ 絶対ルール

1. **まずDBから「要フォロー」を自動検出する**
2. **Layer 1は四半期に1回必ず連絡する**
3. **Give→Give→Giveの精神を忘れない**
4. **完了時に必ずファイル保存を実行する**

---

## STEP 構成

### ▶ STEP 1：人脈状況の確認

```bash
sqlite3 ~/Documents/会社運営DB/db/company.db << 'SQL'
SELECT
  name, company, category,
  last_contact,
  CAST(julianday('now') - julianday(last_contact) AS INTEGER) as days_since,
  CASE
    WHEN category IN ('mentor','partner') AND
         julianday('now') - julianday(last_contact) > 90 THEN '🔴 Layer1 要連絡'
    WHEN julianday('now') - julianday(last_contact) > 180 THEN '🟡 半年超'
    ELSE '🟢 OK'
  END as status
FROM network
WHERE category NOT IN ('expert')
ORDER BY last_contact ASC
LIMIT 20;
SQL
```

**出力：**

```
## 📋 業界人脈メンテナンス（{今日の日付}）

### 今月連絡を取るべき人

| 名前 | 会社 | 関係 | 最終コンタクト | 経過 | 状況 |
|------|------|------|------------|------|------|
| {名前} | {会社} | {関係} | {日付} | {N日} | 🔴/🟡 |

---

### 今月のアクション提案

{要フォローの人ごとに連絡方法・話題を提案}
```

---

### ▶ STEP 2：連絡文の生成 + 参加コミュニティの整理 + 保存

**連絡文の生成（inbox-managementスキルと連携）：**

```
## 連絡文ドラフト

### {名前}さんへ（Layer 1・{N日ぶり}）

{名前}さん

お久しぶりです。最近{自分の近況1文}でした。
{名前}さんの{最近の活動・投稿・近況への言及}が気になっていました。

近々また{ランチ/オンライン}でお話しできますか？

{署名}
```

**コミュニティ・イベント管理：**

```
## 定期参加コミュニティ一覧

| コミュニティ名 | 頻度 | 形式 | 次回日程 | メモ |
|------------|------|------|---------|------|
| {コミュニティ} | 月1回 | オンライン | {日付} | |

## 今年参加予定のイベント

| イベント | 時期 | 目的 |
|---------|------|------|
| {イベント} | {月} | {新規接点 / 既存深化} |
```

**💾 保存：**

```bash
cat > "$HOME/Documents/会社運営DB/records/15_ネットワーク/network-maintenance-{YYYYMM}.md" << 'EOF'
{全文}
EOF

# コンタクトした人の最終連絡日を更新
sqlite3 "$HOME/Documents/会社運営DB/db/company.db" \
  "UPDATE network SET last_contact=date('now') WHERE name='{連絡した人の名前}';"
echo "✅ 人脈メンテナンス記録完了"
```
