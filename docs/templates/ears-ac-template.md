# T-025-01: EARS Acceptance Criteria Template

Build-Factory の全タスクの `acceptance_criteria[].type` は以下 5 形式のいずれか。
CLAUDE.md §3 EARS notation + `backend/schemas/ears_ac_schema.json` で機械的検証。

## EARS 5 形式

### 1. UBIQUITOUS (常時)

「常に成立する性質」。前置条件なし。

```
The system **shall** {要件}.
```

例:
> The intent_classifier service shall provide a unified read API that runs the 3 existing detectors in parallel.

### 2. EVENT-DRIVEN (イベント駆動)

「特定のイベント発生時に成立する」。

```
When [event], the system **shall** {要件}.
```

例:
> When `classify()` is invoked, the system shall execute the 3 detectors in parallel via asyncio and emit an audit_logs entry within 2 seconds.

### 3. STATE-DRIVEN (状態駆動)

「特定の状態の間、成立し続ける」。

```
While [state], the system **shall** {要件}.
```

例:
> While the classifier is active, the system shall preserve the existing 3 detector module symbol surfaces (REFACTOR backwards-compat).

### 4. OPTIONAL (オプション機能)

「機能 enabled の場合に成立する」。

```
Where [feature is enabled], the system **shall** {要件}.
```

例:
> Where the user opts in to Obsidian sync, the system shall mirror Tier 3 facts to ~/Documents/会社運営DB/obsidian/.

### 5. UNWANTED (異常系)

「望ましくない状態を防ぐ」。常に最低 1 件含める (validate-tickets.py で強制)。

```
If [unwanted condition], the system **shall** {reject / fail / not mutate} ...
```

例:
> If invalid persona / unauthorized actor / unknown session is detected, the system shall reject with 4xx {detail:{code,message}} and shall not mutate persistent state.

## tickets.json の AC 形式 (JSON Schema 準拠)

```json
{
  "type": "UBIQUITOUS",
  "text": "The system shall ..."
}
```

JSON Schema: [`backend/schemas/ears_ac_schema.json`](../../backend/schemas/ears_ac_schema.json)

### 必須事項

- `type` は 5 形式 (or レガシー alias EVENT/STATE) のいずれか
- `text` は 20-2000 文字
- type に応じた接続詞 (When / While / Where / If / shall) を含む

### Build-Factory 規約 (追加)

- 各タスクの AC は **最低 3 件**, うち **UNWANTED 必須**
- generic 文言 ("shall implement T-XXX as specified") は **禁止** (本セッションで一括除去済)
- adr_link を含む場合は ADR への cross-reference を明示

## 検証コマンド

```bash
# 全 tickets を JSON Schema で検証
python3 scripts/validate-ears-ac.py

# 単一タスク
python3 scripts/validate-ears-ac.py --task-id T-M27-02

# verbose (各 AC ごとの結果)
python3 scripts/validate-ears-ac.py --verbose
```

## Cross-reference

- `scripts/validate-tickets.py` : 既存 validator (緩い check)
- `scripts/validate-ears-ac.py` : 本 PR で追加 (JSON Schema 厳格 check)
- `scripts/audit-ac-coherence.py` : AC ↔ implementation の整合 audit
- CLAUDE.md §3 EARS notation : 公式定義
