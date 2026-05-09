# 技術スタック選定レポート

**プロジェクト:** {{PROJECT_NAME}}  
**作成日:** {{DATE}}  
**担当:** ENGINE BASE / 高本 聖斗  
**バージョン:** v1.0

---

## プロジェクト分類

| 項目 | 内容 |
|------|------|
| アプリ種別 | {{APP_TYPE}} |
| 規模 | {{SCALE}} |
| 開発スピード | {{SPEED}} |
| 予算帯 | {{BUDGET}} |
| ノーコード判定 | {{NOCODE_JUDGMENT}} |
| 運用担当 | {{OPERATOR}} |

---

## 推奨スタック

### 🟢 第1案（推奨）: {{STACK_1_NAME}}

| レイヤー | 技術 | 選定理由 |
|---------|------|---------|
| フロントエンド | {{FRONTEND_1}} | {{FRONTEND_1_REASON}} |
| バックエンド / BaaS | {{BACKEND_1}} | {{BACKEND_1_REASON}} |
| データベース | {{DB_1}} | {{DB_1_REASON}} |
| 認証 | {{AUTH_1}} | {{AUTH_1_REASON}} |
| インフラ / ホスティング | {{INFRA_1}} | {{INFRA_1_REASON}} |
| 決済 | {{PAYMENT_1}} | {{PAYMENT_1_REASON}} |
| メール / 通知 | {{NOTIFICATION_1}} | {{NOTIFICATION_1_REASON}} |
| CMS（該当時） | {{CMS_1}} | {{CMS_1_REASON}} |

**ENGINE BASE 習熟度:** {{PROFICIENCY_1}}  
**インフラ月額目安:** {{MONTHLY_COST_1}}  
**開発工数目安:** {{DEV_HOURS_1}}  

**✅ メリット**
{{PROS_1}}

**⚠️ デメリット・リスク**
{{CONS_1}}

---

### 🔵 第2案（代替）: {{STACK_2_NAME}}

| レイヤー | 技術 | 選定理由 |
|---------|------|---------|
| フロントエンド | {{FRONTEND_2}} | {{FRONTEND_2_REASON}} |
| バックエンド / BaaS | {{BACKEND_2}} | {{BACKEND_2_REASON}} |
| データベース | {{DB_2}} | {{DB_2_REASON}} |
| 認証 | {{AUTH_2}} | — |
| インフラ / ホスティング | {{INFRA_2}} | — |
| 決済 | {{PAYMENT_2}} | — |

**ENGINE BASE 習熟度:** {{PROFICIENCY_2}}  
**インフラ月額目安:** {{MONTHLY_COST_2}}  
**開発工数目安:** {{DEV_HOURS_2}}  

**✅ メリット**
{{PROS_2}}

**⚠️ デメリット・リスク**
{{CONS_2}}

---

## 意思決定ポイント

| こちらを重視するなら | 推奨案 |
|---------------------|--------|
| 開発スピード・コスト削減 | {{SPEED_PRIORITY_CHOICE}} |
| スケーラビリティ・将来の拡張 | {{SCALE_PRIORITY_CHOICE}} |
| 運用の内製化・エンジニア引き継ぎ | {{HANDOVER_PRIORITY_CHOICE}} |
| ノーコードで早く出す | {{NOCODE_PRIORITY_CHOICE}} |

---

## ENGINE BASE 過去実績

過去に類似プロジェクトで採用した構成と結果：

{{PAST_PROJECTS_TABLE}}

---

## インフラコスト試算

| 項目 | 月額目安（第1案） | 月額目安（第2案） |
|------|----------------|----------------|
| フロントエンド | {{INFRA_COST_FRONTEND_1}} | {{INFRA_COST_FRONTEND_2}} |
| バックエンド / DB | {{INFRA_COST_BACKEND_1}} | {{INFRA_COST_BACKEND_2}} |
| 認証 | {{INFRA_COST_AUTH_1}} | {{INFRA_COST_AUTH_2}} |
| メール | {{INFRA_COST_EMAIL_1}} | {{INFRA_COST_EMAIL_2}} |
| **合計目安** | **{{INFRA_COST_TOTAL_1}}** | **{{INFRA_COST_TOTAL_2}}** |

> ※上記はスモールスタート時の目安。ユーザー数・機能追加により変動します。

---

## 確認事項・ご質問

{{OPEN_QUESTIONS}}

---

## 次のステップ

ご確認いただき、方向性をご選択ください。  
確定後 → **`architecture-design` スキル**でシステム全体の詳細設計に進みます。

**ご質問・ご不明点はお気軽にどうぞ。**

---

*作成: ENGINE BASE / 高本 聖斗 | TEL: 090-1180-5989 | info@engine-base.com*
