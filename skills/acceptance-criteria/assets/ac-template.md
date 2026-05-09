# 受け入れ基準 - {{FEATURE_NAME}}

**作成日:** {{CREATED_DATE}}
**作成者:** {{CREATED_BY}}
**対象スプリント:** {{SPRINT_NUMBER}}
**ステータス:** {{STATUS}}（Draft / Review / Approved）

---

## {{STORY_TITLE}}

**ユーザーストーリー:** {{USER_STORY}}

**優先度:** {{PRIORITY}}
**見積もり:** {{STORY_POINTS}}pt

---

## 前提条件

{{PRECONDITIONS}}

---

## 受け入れ基準

### 正常系

#### AC-001: {{AC_001_TITLE}}
**概要:** {{AC_001_SUMMARY}}

```gherkin
Given {{GIVEN_001}}
When  {{WHEN_001}}
Then  {{THEN_001}}
```

---

#### AC-002: {{AC_002_TITLE}}
**概要:** {{AC_002_SUMMARY}}

```gherkin
Given {{GIVEN_002}}
When  {{WHEN_002}}
Then  {{THEN_002}}
```

---

### 異常系

#### AC-{{ERROR_AC_NUM}}: {{ERROR_AC_TITLE}}
**概要:** {{ERROR_AC_SUMMARY}}

```gherkin
Given {{GIVEN_ERROR}}
When  {{WHEN_ERROR}}
Then  {{THEN_ERROR}}
```

---

### 境界値

#### AC-{{BOUNDARY_AC_NUM}}: {{BOUNDARY_AC_TITLE}}
**概要:** {{BOUNDARY_AC_SUMMARY}}

```gherkin
Given {{GIVEN_BOUNDARY}}
When  {{WHEN_BOUNDARY}}
Then  {{THEN_BOUNDARY}}
```

---

## AC一覧サマリー

| ID | タイトル | 種別 | 優先度 | テスト担当 |
|----|---------|------|--------|----------|
{{AC_SUMMARY_ROWS}}

---

## スコープ外

{{OUT_OF_SCOPE}}

---

## 備考・補足

{{NOTES}}

---

*作成日: {{CREATED_DATE}} / 作成者: {{CREATED_BY}} / 承認者: {{APPROVER}}*
