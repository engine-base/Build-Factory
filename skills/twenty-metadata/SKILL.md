---
name: twenty-metadata
description: Twenty CRM の Metadata API を使ってカスタムオブジェクト・フィールド・リレーションを作成・更新・削除するスキル。「オブジェクトを追加したい」「フィールドを増やしたい」「テーブル構造を変えたい」「リレーションを作りたい」という場面で起動する。全オブジェクト・全フィールド型に対応。
tab: 設計
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 1. 出力前の必須内部チェック（ユーザーには見せない）

出力を生成する前に、以下を内部で確認する：

- ユーザーの業界・ドメインに固有の法律・規制・制度を参照したか
- 仮説は「売上を上げたい」のような汎用ゴールではなく、そのドメイン・業務フローに固有の仮説になっているか
- 質問は「はい/いいえ」で終わらず、具体例や選択肢を含む設計になっているか
- 曖昧な発言（複数の解釈が可能な表現）に対して複数の解釈を提示したか
- ステークホルダー全員の視点（承認者・反対する人・実際の利用者）を漏らしていないか

---

### 2. 質問保留・打ち合わせ優先ルール（全スキル共通）

クライアントから以下のような発言があった場合、即座に質問の送信を停止する：
- 「質問は打ち合わせで」「後で回答します」「今は答えられない」

**この状況での正しい対応：**
1. 現時点で受け取っているすべての情報を整理・構造化して出力する
2. 未確認事項は「打ち合わせで確認する事項リスト」として明示する
3. 次のSTEPへの準備完了を宣言する
4. 絶対に追加の質問を投げない

---

## 🏗️ Twenty Metadata API スキル

### 概要

Twenty CRM の Metadata API（`http://localhost:3000/metadata`）をGraphQLで操作し、データモデルの設計・変更を行う。

**認証**:
```
Authorization: Bearer ${TWENTY_API_TOKEN}
Content-Type: application/json
```

環境変数 `TWENTY_API_TOKEN` を使用。未設定の場合はユーザーに確認する。

---

## STEP 1: 現状把握

操作開始前に必ず既存のオブジェクト一覧を取得して把握する。

### オブジェクト一覧取得

```graphql
# POST http://localhost:3000/metadata
query GetObjects {
  objects(paging: { first: 100 }) {
    edges {
      node {
        id
        nameSingular
        namePlural
        labelSingular
        labelPlural
        description
        isCustom
        isActive
        fields(paging: { first: 50 }) {
          edges {
            node {
              id
              name
              label
              type
              isCustom
              isActive
            }
          }
        }
      }
    }
  }
}
```

---

## STEP 2: オブジェクト操作

### オブジェクト作成

```graphql
mutation CreateObject {
  createOneObject(input: {
    nameSingular: "project"           # キャメルケース・単数形
    namePlural: "projects"            # キャメルケース・複数形
    labelSingular: "プロジェクト"      # 表示名（単数）
    labelPlural: "プロジェクト一覧"   # 表示名（複数）
    description: "開発プロジェクトの管理"
    icon: "IconBriefcase"             # twenty-ui のアイコン名
  }) {
    id
    nameSingular
    namePlural
    labelSingular
  }
}
```

**icon の選択肢（主要なもの）**:
| 用途 | アイコン名 |
|---|---|
| プロジェクト | IconBriefcase |
| 機能 | IconPuzzle |
| スプリント | IconRocket |
| 要件 | IconFileText |
| タスク | IconCheckbox |
| AI | IconRobot |
| 設定 | IconSettings |

### オブジェクト更新

```graphql
mutation UpdateObject {
  updateOneObject(
    idToUpdate: "オブジェクトのid"
    input: {
      labelSingular: "新しい表示名"
      description: "更新後の説明"
      isActive: true
    }
  ) {
    id
    labelSingular
  }
}
```

### オブジェクト削除

```graphql
mutation DeleteObject {
  deleteOneObject(idToDelete: "オブジェクトのid") {
    id
  }
}
```

---

## STEP 3: フィールド操作

### フィールド一覧取得（オブジェクト指定）

```graphql
query GetFields {
  fields(paging: { first: 100 }) {
    edges {
      node {
        id
        name
        label
        type
        description
        isCustom
        isActive
        objectMetadataId
        defaultValue
        options {
          id
          value
          label
          color
          position
        }
      }
    }
  }
}
```

### フィールド作成 — テキスト型

```graphql
mutation CreateTextField {
  createOneField(input: {
    objectMetadataId: "オブジェクトのid"
    type: TEXT
    name: "fieldName"
    label: "フィールド名"
    description: "フィールドの説明"
    defaultValue: ""
    isNullable: true
  }) {
    id
    name
    type
  }
}
```

### フィールド作成 — 数値型

```graphql
mutation CreateNumberField {
  createOneField(input: {
    objectMetadataId: "オブジェクトのid"
    type: NUMBER
    name: "estimatedHours"
    label: "見積もり工数"
    defaultValue: 0
    isNullable: true
  }) { id name type }
}
```

### フィールド作成 — 日付型

```graphql
mutation CreateDateField {
  createOneField(input: {
    objectMetadataId: "オブジェクトのid"
    type: DATE_TIME
    name: "startDate"
    label: "開始日"
    isNullable: true
  }) { id name type }
}
```

### フィールド作成 — 真偽値型

```graphql
mutation CreateBooleanField {
  createOneField(input: {
    objectMetadataId: "オブジェクトのid"
    type: BOOLEAN
    name: "isActive"
    label: "アクティブ"
    defaultValue: true
    isNullable: false
  }) { id name type }
}
```

### フィールド作成 — セレクト型（ステータスなど）

```graphql
mutation CreateSelectField {
  createOneField(input: {
    objectMetadataId: "オブジェクトのid"
    type: SELECT
    name: "status"
    label: "ステータス"
    options: [
      { value: "PLANNING", label: "計画中", color: "GRAY", position: 0 }
      { value: "ACTIVE", label: "進行中", color: "BLUE", position: 1 }
      { value: "REVIEW", label: "レビュー中", color: "ORANGE", position: 2 }
      { value: "DONE", label: "完了", color: "GREEN", position: 3 }
      { value: "PAUSED", label: "停止中", color: "RED", position: 4 }
    ]
    defaultValue: "'PLANNING'"
    isNullable: false
  }) { id name type }
}
```

**color の選択肢**: `GRAY`, `RED`, `PINK`, `PURPLE`, `BLUE`, `CYAN`, `GREEN`, `YELLOW`, `ORANGE`, `TURQUOISE`

### フィールド作成 — マルチセレクト型

```graphql
mutation CreateMultiSelectField {
  createOneField(input: {
    objectMetadataId: "オブジェクトのid"
    type: MULTI_SELECT
    name: "tags"
    label: "タグ"
    options: [
      { value: "FRONTEND", label: "フロントエンド", color: "BLUE", position: 0 }
      { value: "BACKEND", label: "バックエンド", color: "GREEN", position: 1 }
      { value: "AI", label: "AI", color: "PURPLE", position: 2 }
    ]
    isNullable: true
  }) { id name type }
}
```

### フィールド更新

```graphql
mutation UpdateField {
  updateOneField(
    idToUpdate: "フィールドのid"
    objectMetadataId: "オブジェクトのid"
    input: {
      label: "新しいラベル"
      description: "更新後の説明"
      isActive: true
    }
  ) { id name label }
}
```

### フィールド削除

```graphql
mutation DeleteField {
  deleteOneField(
    idToDelete: "フィールドのid"
    objectMetadataId: "オブジェクトのid"
  ) { id }
}
```

---

## STEP 4: リレーション操作

### リレーション作成（1対多）

```graphql
mutation CreateRelation {
  createOneRelation(input: {
    relationType: ONE_TO_MANY
    fromObjectMetadataId: "プロジェクトのid"    # 1側
    toObjectMetadataId: "フィーチャーのid"       # 多側
    fromName: "features"
    toName: "project"
    fromLabel: "機能一覧"
    toLabel: "プロジェクト"
    fromDescription: "このプロジェクトに属する機能"
    toDescription: "この機能が属するプロジェクト"
  }) {
    id
    relationType
  }
}
```

### リレーション作成（多対多）

```graphql
mutation CreateManyToManyRelation {
  createOneRelation(input: {
    relationType: MANY_TO_MANY
    fromObjectMetadataId: "スプリントのid"
    toObjectMetadataId: "フィーチャーのid"
    fromName: "features"
    toName: "sprints"
    fromLabel: "機能"
    toLabel: "スプリント"
  }) { id relationType }
}
```

---

## STEP 5: 実行後の確認

操作完了後は必ず以下を確認する：

1. **オブジェクト一覧を再取得**して変更が反映されているか確認
2. **エラーがあれば原因を分析**して修正案を提示
3. **フロントエンドへの反映確認**：`http://localhost:3001` で新オブジェクトが表示されているか確認するようユーザーに案内する

---

## 注意事項

- カスタムオブジェクト（isCustom: true）のみ変更可能。標準オブジェクト（Company, People等）のスキーマは変更不可
- フィールド名（name）は camelCase で指定する
- 削除は元に戻せない。削除前に必ずユーザーに確認する
- `TWENTY_API_TOKEN` は Twenty の Settings > API & Webhooks から取得する
