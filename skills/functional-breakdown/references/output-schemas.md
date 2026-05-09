# 出力 JSON スキーマ詳細

`functional-breakdown` STEP 3 で出力する 4 種 JSON の完全スキーマ。
これらの JSON は `architecture-design` スキルの STEP 4.5 (選定モジュール) の入力として消費される。

---

## screens.json

```json
{
  "version": "1.0",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "items": [
    {
      "id": "S-001",
      "name": "商品一覧",
      "description": "ユーザーが購入対象の商品をブラウズする画面",
      "fields": [
        {"name": "title", "type": "string", "label": "商品名", "required": true},
        {"name": "price", "type": "number", "label": "価格", "required": true},
        {"name": "stock", "type": "number", "label": "在庫数", "required": false},
        {"name": "thumbnail", "type": "image", "label": "サムネ", "required": true}
      ],
      "layout": "grid",
      "actions": ["search", "filter", "sort", "favorite", "add_to_cart"],
      "states": ["loading", "empty", "error"],
      "transitions": {
        "from": ["S-000"],
        "to": ["S-002", "S-010"]
      },
      "responsive": {"pc": true, "sp": true, "tablet": true},
      "access_roles": ["R-001", "R-002", "R-003"],
      "edit_roles": ["R-003"],
      "related_apis": ["GET /api/products"],
      "related_entities": ["E-002"],
      "checklist": [
        {"key": "CL-S-1", "label": "表示項目", "status": "ok", "notes": "title/price/stock/thumb"},
        {"key": "CL-S-2", "label": "レイアウト", "status": "ok", "notes": "grid"},
        {"key": "CL-S-3", "label": "操作ボタン", "status": "ok"},
        {"key": "CL-S-4", "label": "検索/フィルタ/ソート", "status": "ok"},
        {"key": "CL-S-5", "label": "ページング", "status": "ok"},
        {"key": "CL-S-6", "label": "状態の表示", "status": "ok"},
        {"key": "CL-S-7", "label": "遷移", "status": "ok"},
        {"key": "CL-S-8", "label": "レスポンシブ", "status": "ok"},
        {"key": "CL-S-9", "label": "閲覧権限", "status": "ok"},
        {"key": "CL-S-10", "label": "編集権限", "status": "ok"},
        {"key": "CL-S-11", "label": "関連 API", "status": "ok"},
        {"key": "CL-S-12", "label": "関連エンティティ", "status": "ok"}
      ],
      "status": "decided",
      "decided_at": "2026-05-09T10:30:00Z",
      "blocked_reason": null
    }
  ]
}
```

### フィールド型一覧
- 基本: `string` / `number` / `boolean` / `date` / `datetime`
- 拡張: `image` / `file` / `richtext` / `json` / `enum:[a,b,c]` / `array<string>` / `relation:E-XXX`

### layout 値
- `grid` / `table` / `card` / `form` / `hybrid` / `list` / `kanban` / `timeline` / `dashboard`

### actions 値
- CRUD: `create` / `read` / `update` / `delete`
- 検索系: `search` / `filter` / `sort`
- 操作系: `favorite` / `share` / `comment` / `vote` / `export` / `import`
- E-commerce: `add_to_cart` / `purchase` / `wishlist`
- カスタム: 文字列で自由に追加可

---

## features.json

```json
{
  "version": "1.0",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "items": [
    {
      "id": "F-001",
      "name": "メール認証ログイン",
      "category": "auth",
      "description": "メールアドレス + パスワードでログインし、必要に応じて 2FA を要求",
      "happy_path": [
        "1. メール + パスワード入力",
        "2. サーバ側でハッシュ照合",
        "3. 2FA 有効ならコード入力画面",
        "4. JWT 発行 → セッション開始"
      ],
      "error_paths": [
        {"trigger": "パスワード不一致 5 回", "behavior": "15 分ロック + メール通知"},
        {"trigger": "未認証アカウント", "behavior": "認証メール再送導線を表示"}
      ],
      "policies": {
        "password_min_length": 12,
        "password_strength": "大小英数記号必須",
        "session_ttl": "24h",
        "refresh_token_ttl": "7d",
        "rate_limit_per_min": 5
      },
      "notifications": [
        {"event": "login_success_new_device", "channel": "email", "to": "user", "frequency": "always"},
        {"event": "login_failed_5x", "channel": "email", "to": "user", "frequency": "once_per_lock"}
      ],
      "audit_logs": ["login_success", "login_failed", "password_change", "2fa_enabled"],
      "access_roles": ["R-001", "R-002", "R-003"],
      "external_services": ["SendGrid", "reCAPTCHA v3"],
      "related_screens": ["S-100", "S-101", "S-102"],
      "related_entities": ["E-001", "E-005"],
      "related_apis": ["POST /api/auth/login", "POST /api/auth/logout", "POST /api/auth/2fa/verify"],
      "auth_specific": {
        "login_methods": ["email_password", "google_oauth", "magic_link"],
        "password_reset": "email_token_30min",
        "two_factor": {"required_for": ["R-003"], "methods": ["totp", "backup_code"]},
        "lockout_policy": {"attempts": 5, "duration_min": 15},
        "withdrawal": {"flow": "30day_grace", "data_retention_days": 90, "legal_keep": ["invoices"]},
        "social_unlink": "allowed_if_password_set_and_not_last"
      },
      "checklist": [...],
      "status": "decided",
      "decided_at": "2026-05-09T11:00:00Z"
    }
  ]
}
```

### category 値
- `auth` / `payment` / `notification` / `search` / `sharing` / `crud` / `analytics` / `import_export` / `realtime` / `admin` / `other`

`category=auth` のときのみ `auth_specific` ブロックを含める (8 つの認証拡張チェックリスト対応)。

---

## roles.json

```json
{
  "version": "1.0",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "roles": [
    {
      "id": "R-001",
      "key": "guest",
      "name": "ゲスト",
      "description": "未ログインの訪問者",
      "default_for_new_users": false,
      "assignable_by": []
    },
    {
      "id": "R-002",
      "key": "user",
      "name": "一般会員",
      "description": "ログイン済みの購入者",
      "default_for_new_users": true,
      "assignable_by": ["R-003"]
    },
    {
      "id": "R-003",
      "key": "admin",
      "name": "管理者",
      "description": "サイト運営者",
      "default_for_new_users": false,
      "assignable_by": ["R-003"]
    }
  ],
  "matrix": {
    "S-001": {"R-001": ["read"], "R-002": ["read"], "R-003": ["read", "create", "update", "delete"]},
    "S-002": {"R-001": ["read"], "R-002": ["read"], "R-003": ["read", "update", "delete"]},
    "F-001": {"R-001": ["execute"], "R-002": ["execute"], "R-003": ["execute"]},
    "F-005": {"R-003": ["execute"]}
  },
  "object_constraints": [
    {"role": "R-002", "entity": "E-003", "constraint": "owned_by_self", "description": "自分の注文のみ閲覧可"},
    {"role": "R-002", "entity": "E-006", "constraint": "owned_by_organization", "description": "同一組織内のみ"}
  ]
}
```

### matrix の値
キー = `S-XXX` または `F-XXX` (画面 / 機能 ID) / 値 = ロール ID → 操作の配列

### 操作の語彙
- 画面: `read` / `create` / `update` / `delete` / `export`
- 機能: `execute` / `view_audit`
- カスタム可

### object_constraints
- `owned_by_self` — 本人のレコードのみ
- `owned_by_organization` — 同一組織のレコードのみ
- `owned_by_team` — 同一チームのレコードのみ
- `public_only` — 公開フラグ true のもののみ
- `custom:rule_name` — プロジェクト固有ルール

---

## entities.json

```json
{
  "version": "1.0",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "entities": [
    {
      "id": "E-001",
      "name": "User",
      "description": "システム利用者全般",
      "fields": [
        {"name": "id", "type": "uuid", "pk": true, "required": true},
        {"name": "email", "type": "string", "unique": true, "required": true, "max_length": 255},
        {"name": "password_hash", "type": "string", "required": true},
        {"name": "role_id", "type": "fk:R-XXX", "required": true},
        {"name": "two_factor_secret", "type": "string", "required": false, "encrypted": true},
        {"name": "created_at", "type": "datetime", "required": true},
        {"name": "updated_at", "type": "datetime", "required": true},
        {"name": "deleted_at", "type": "datetime", "required": false}
      ],
      "relations": [
        {"to": "E-002", "kind": "1:N", "fk": "user_id", "description": "1 ユーザーが複数注文"},
        {"to": "E-005", "kind": "1:N", "fk": "user_id", "description": "ログイン試行履歴"}
      ],
      "soft_delete": true,
      "timestamps": true,
      "tenant_field": "account_id",
      "indexes": [
        {"fields": ["email"], "unique": true},
        {"fields": ["account_id", "created_at"]}
      ],
      "computed": [
        {"name": "order_count", "from": "COUNT(E-002 WHERE user_id)"},
        {"name": "lifetime_value", "from": "SUM(E-002.amount WHERE user_id AND status=paid)"}
      ],
      "checklist": [...],
      "status": "decided",
      "decided_at": "2026-05-09T12:00:00Z"
    }
  ]
}
```

### fields の型
- スカラー: `uuid` / `serial` / `string` / `text` / `number` / `decimal` / `boolean` / `date` / `datetime`
- バイナリ系: `image` / `file` / `binary`
- 構造: `json` / `jsonb` / `array<T>`
- 関係: `fk:E-XXX` / `fk:R-XXX`
- 暗号化フラグ: `encrypted: true` で at-rest 暗号化推奨を示す

### relations の kind
- `1:1` / `1:N` / `N:1` / `N:N` / `polymorphic`

`N:N` の場合は中間テーブルを別エンティティ (E-XXX) として定義する。

---

## ステータス遷移と decided_at

```
draft ──[ユーザーが詰める開始]──> in_review ──[全 CL ok]──> decided
                                       │
                                       └─[確認待ち]─> blocked
                                                       │
decided ──[変更したい]──> in_review                    └─[確認完了]─> in_review
```

`decided_at` は status が decided になった瞬間の ISO8601 UTC タイムスタンプ。
`blocked` の場合は必須フィールド `blocked_reason: { reason: string, ask_to: string, due: date | null }`。

---

## architecture-design への引き継ぎマッピング

| functional-breakdown 出力 | architecture-design STEP 4.5 での使い方 |
|---|---|
| `features[].external_services[]` | ライブラリ/OSS 選定の用途リストに追加 |
| `features[].category=auth` の `auth_specific` | 認証ライブラリ候補の絞り込み |
| `features[].category=payment` | 決済代行候補の絞り込み |
| `features[].category=search` のスケール感 | 全文検索エンジン要否判定 |
| `roles[].length` + `matrix` の複雑度 | RBAC ライブラリ要否判定 |
| `entities[].length` と `relations` の複雑度 | DB / ORM 候補の絞り込み |
| `entities[].fields[].encrypted` | KMS / 暗号化要件 |
| `features[].policies.rate_limit_per_min` | レートリミットライブラリ要否 |
| `features[].notifications[]` | メール / Push 送信サービス候補 |
