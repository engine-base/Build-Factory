# ADR-007: EARS notation 必須

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: 高本まさと

## Context

タスクの **acceptance_criteria (AC)** は AI 社員 (devon, quinn) が「実装が完了したか」を判定する根拠。

従来の自然言語の AC は曖昧:
- ❌ "ログイン画面で正しくログインできること"
- → どの状態で? 失敗時は? 同時複数セッションは?

要件:
- **AI 社員が一意に解釈できる**
- **テストコードに自動変換できる**
- **AC の網羅性をチェックできる** (4 状態: 通常 / イベント駆動 / 状態駆動 / 異常系)

候補:
- **Gherkin (Given/When/Then)** = BDD 標準だが冗長
- **EARS (Easy Approach to Requirements Syntax)** = NASA / 自動車業界で実績、5 形式でカテゴリ分類
- **自由記述** = 曖昧、AI 解釈エラー多発

## Decision

**EARS notation の 5 形式** を全 acceptance_criteria で必須とする:

### 1. UBIQUITOUS (常時)
```
The system shall <要求>
```
例: "The system **shall** support BtoB pricing tiers for every product SKU."

### 2. EVENT-DRIVEN (イベント駆動)
```
When <event>, the system shall <要求>
```
例: "**When** a customer places a bundle order, the system **shall** deduct stock for each constituent SKU."

### 3. STATE-DRIVEN (状態駆動)
```
While <state>, the system shall <要求>
```
例: "**While** a subscription is paused, the system **shall** not generate billing."

### 4. OPTIONAL (機能フラグ)
```
Where <feature is enabled>, the system shall <要求>
```
例: "**Where** 2FA is enabled for a user, the system **shall** require TOTP on every login."

### 5. UNWANTED (異常系)
```
If <unwanted condition>, the system shall not <禁止事項> [and shall <代替>]
```
例: "**If** payment authorization fails, the system **shall not** ship the order **and shall** notify the customer."

## ルール

- 全タスクの `acceptance_criteria` で **5 形式のいずれか** に分類して書く
- **必ず英語で書く** (AI が一意解釈できるため、日本語の曖昧さ回避)
- 1 タスクに **最低 3 件**、目安 5-7 件
- **少なくとも 1 件は UNWANTED 形式** (異常系の網羅性担保)
- **各 AC に対し最低 1 件のテストケース** が紐づく

## EARS バリデータ (T-008b-02 で実装予定)

タスク作成時に自動チェック:
1. 5 形式のいずれかに当てはまるか (正規表現マッチ)
2. UNWANTED 形式が最低 1 件あるか
3. AC 数が 3-7 件の範囲か
4. "shall" が必ず使われているか (should/must は禁止)

## Consequences

### 得られるもの
- ✅ AI 社員が一意解釈できる → 実装ぶれが減る
- ✅ テストカバレッジ計算しやすい (AC 数 = 最低テスト数)
- ✅ 異常系の漏れがない (UNWANTED 必須化)
- ✅ NASA / 自動車業界の実績で安定性高い

### 諦めるもの
- ❌ 学習コスト: 5 形式の使い分けに慣れが必要
  - → AI (mary BA) が初稿生成、masato が承認するワークフロー
- ❌ 英語必須 → 日本語派生の「shall」表現の不統一を避けるため英語固定
  - → 日本語 UI 表示時はサーバ側で訳す or 別フィールドで日本語訳保持

### 関連
- 影響を受けるタスク: T-008b-01 (EARS パーサ) / T-008b-02 (バリデータ) / T-008b-03 (UNWANTED 検証)
- 参考: [EARS の発明者 Alistair Mavin (Rolls-Royce)](https://alistairmavin.com/ears/)
