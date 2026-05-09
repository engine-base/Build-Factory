---
name: twenty-records
description: Twenty CRM の GraphQL API を使って全オブジェクトのレコードを作成・取得・更新・削除するスキル。「データを追加したい」「レコードを検索したい」「一覧を取得したい」「CRMの情報を更新したい」という場面で起動する。Company / People / Opportunity / Task / Note およびカスタムオブジェクト全てに対応。
tab: 設計
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 1. 出力前の必須内部チェック（ユーザーには見せない）

出力を生成する前に、以下を内部で確認する：

- ユーザーの業界・ドメインに固有の法律・規制・制度を参照したか
- 仮説は汎用ゴールではなく、そのドメイン・業務フローに固有の仮説になっているか
- 曖昧な発言に対して複数の解釈を提示したか

---

### 2. 質問保留・打ち合わせ優先ルール（全スキル共通）

クライアントから以下のような発言があった場合、即座に質問の送信を停止する。
現時点の情報を整理・構造化して出力し、追加質問は投げない。

---

## 📦 Twenty Records API スキル

### 概要

Twenty CRM の GraphQL API（`http://localhost:3000/graphql`）でレコードを操作する。

**認証**:
```
Authorization: Bearer ${TWENTY_API_TOKEN}
Content-Type: application/json
```

**オブジェクト名の命名規則**:
- クエリ/ミューテーション名は camelCase の複数形（例: `companies`, `people`, `opportunities`）
- カスタムオブジェクトも同様（例: `projects`, `features`, `sprints`）

---

## STEP 1: レコード一覧取得

### 基本的な一覧取得

```graphql
# POST http://localhost:3000/graphql
query GetCompanies {
  companies(
    first: 20
    orderBy: { createdAt: DescNullsLast }
  ) {
    edges {
      node {
        id
        name
        domainName { primaryLinkUrl }
        employees
        createdAt
        updatedAt
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
    totalCount
  }
}
```

### フィルター付き取得

```graphql
query GetFilteredOpportunities {
  opportunities(
    filter: {
      stage: { eq: "NEW" }
      amount: { amountMicros: { gte: "1000000" } }
    }
    orderBy: { createdAt: DescNullsLast }
    first: 50
  ) {
    edges {
      node {
        id
        name
        stage
        amount { amountMicros currencyCode }
        closeDate
        company { id name }
        pointOfContact { id name { firstName lastName } }
      }
    }
    totalCount
  }
}
```

### ページネーション（カーソルベース）

```graphql
query GetNextPage {
  companies(
    first: 20
    after: "前ページの endCursor"
  ) {
    edges { node { id name } }
    pageInfo { hasNextPage endCursor }
  }
}
```

### 全文検索

```graphql
query SearchRecords {
  companies(
    filter: {
      or: [
        { name: { like: "%検索キーワード%" } }
        { domainName: { primaryLinkUrl: { like: "%検索キーワード%" } } }
      ]
    }
  ) {
    edges { node { id name } }
  }
}
```

---

## STEP 2: レコード1件取得

```graphql
query GetCompany {
  company(id: "レコードのid") {
    id
    name
    domainName { primaryLinkUrl }
    employees
    people {
      edges {
        node {
          id
          name { firstName lastName }
          emails { primaryEmail }
        }
      }
    }
    opportunities {
      edges {
        node {
          id
          name
          stage
          amount { amountMicros currencyCode }
        }
      }
    }
  }
}
```

---

## STEP 3: レコード作成

### Company（企業）作成

```graphql
mutation CreateCompany {
  createCompany(data: {
    name: "株式会社サンプル"
    domainName: { primaryLinkUrl: "https://sample.co.jp", primaryLinkLabel: "" }
    employees: 50
    address: {
      addressStreet1: "東京都渋谷区"
      addressCity: "渋谷区"
      addressCountry: "日本"
    }
  }) {
    id
    name
  }
}
```

### People（担当者）作成

```graphql
mutation CreatePerson {
  createPerson(data: {
    name: { firstName: "太郎", lastName: "田中" }
    emails: { primaryEmail: "tanaka@sample.co.jp" }
    phones: { primaryPhoneNumber: "090-1234-5678", primaryPhoneCountryCode: "+81" }
    company: { id: "企業のid" }
    jobTitle: "開発部 マネージャー"
  }) {
    id
    name { firstName lastName }
  }
}
```

### Opportunity（案件）作成

```graphql
mutation CreateOpportunity {
  createOpportunity(data: {
    name: "Webアプリ開発案件"
    stage: "NEW"
    amount: { amountMicros: "5000000000", currencyCode: "JPY" }
    closeDate: "2025-03-31"
    company: { id: "企業のid" }
    pointOfContact: { id: "担当者のid" }
  }) {
    id
    name
    stage
  }
}
```

### Task（タスク）作成

```graphql
mutation CreateTask {
  createTask(data: {
    title: "要件定義書レビュー"
    body: "添付の要件定義書をレビューして修正点を提出"
    dueAt: "2025-01-15T18:00:00Z"
    status: "TODO"
    assignee: { id: "担当者のid" }
  }) {
    id
    title
    status
  }
}
```

### Note（メモ）作成

```graphql
mutation CreateNote {
  createNote(data: {
    title: "キックオフMTGメモ"
    body: "## 議事録\n\n### 決定事項\n- 開発期間: 3ヶ月\n- 担当エンジニア: 2名"
  }) {
    id
    title
  }
}
```

### カスタムオブジェクト作成（例: Project）

```graphql
mutation CreateProject {
  createProject(data: {
    name: "ECサイトリニューアル"
    status: "ACTIVE"
    startDate: "2025-01-01"
    endDate: "2025-03-31"
    description: "既存ECサイトの全面リニューアル開発"
    company: { id: "企業のid" }
  }) {
    id
    name
    status
  }
}
```

---

## STEP 4: レコード更新

```graphql
mutation UpdateOpportunity {
  updateOpportunity(
    id: "レコードのid"
    data: {
      stage: "WON"
      amount: { amountMicros: "8000000000", currencyCode: "JPY" }
      closeDate: "2025-02-28"
    }
  ) {
    id
    name
    stage
  }
}
```

---

## STEP 5: レコード削除

```graphql
mutation DeleteCompany {
  deleteCompany(id: "レコードのid") {
    id
  }
}
```

---

## STEP 6: 関連レコードの操作

### レコード間のリレーション付け

```graphql
# People を Company に紐づける
mutation AttachPersonToCompany {
  updatePerson(
    id: "担当者のid"
    data: {
      company: { id: "企業のid" }
    }
  ) {
    id
    name { firstName lastName }
    company { id name }
  }
}
```

### 複数レコード一括作成

```graphql
mutation CreateManyTasks {
  createTasks(data: [
    { title: "要件定義", status: "TODO", dueAt: "2025-01-10T18:00:00Z" }
    { title: "基本設計", status: "TODO", dueAt: "2025-01-20T18:00:00Z" }
    { title: "詳細設計", status: "TODO", dueAt: "2025-01-31T18:00:00Z" }
  ]) {
    id
    title
    status
  }
}
```

---

## STEP 7: よく使うフィルター記法

```graphql
# 比較演算子
filter: { employees: { gte: 10, lte: 100 } }     # 範囲
filter: { name: { eq: "完全一致" } }               # 完全一致
filter: { name: { like: "%部分一致%" } }            # 部分一致
filter: { name: { in: ["A社", "B社"] } }            # 複数値
filter: { deletedAt: { is: NULL } }                # NULLチェック

# 論理演算子
filter: {
  and: [
    { stage: { eq: "ACTIVE" } }
    { amount: { amountMicros: { gte: "1000000" } } }
  ]
}
filter: {
  or: [
    { stage: { eq: "NEW" } }
    { stage: { eq: "SCREENING" } }
  ]
}
filter: { not: { stage: { eq: "CLOSED" } } }
```

---

## 注意事項

- `id` は UUID形式（例: `"550e8400-e29b-41d4-a716-446655440000"`）
- 金額は `amountMicros`（マイクロ単位、500万円 = `"5000000000000"`）と `currencyCode`（`"JPY"`）で指定
- 日付は ISO 8601形式（例: `"2025-01-15T09:00:00Z"`）
- 削除前には必ずユーザーに確認する
- `TWENTY_API_TOKEN` は Twenty の Settings > API & Webhooks から取得する
