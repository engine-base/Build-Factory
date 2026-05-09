# プロジェクトスケジュール
プロジェクト名：
作成日：YYYY-MM-DD
バージョン：1.0

## Ganttチャート

```mermaid
gantt
    title プロジェクトスケジュール
    dateFormat YYYY-MM-DD
    excludes weekends

    section フェーズ1: 設計
    要件定義・確認         :done, req, YYYY-MM-DD, 3d
    アーキテクチャ設計      :done, arch, after req, 2d
    API設計               :active, api, after arch, 3d
    クライアント承認ゲート   :milestone, gate1, after api, 0d

    section フェーズ2: 実装
    認証・基盤実装          :impl1, after gate1, 5d
    コア機能実装            :impl2, after impl1, 7d
    フロントエンド実装       :impl3, after impl1, 8d
    クライアント承認ゲート   :milestone, gate2, after impl3, 0d

    section フェーズ3: テスト・納品
    テスト・バグ修正        :test, after gate2, 3d
    UAT（クライアント確認）  :uat, after test, 3d
    修正・最終確認          :fix, after uat, 2d
    納品                   :milestone, delivery, after fix, 0d
```

## マイルストーン一覧
| マイルストーン | 日付 | 成果物 | 承認者 |
|-------------|------|-------|-------|
| 設計完了・承認 | YYYY-MM-DD | 要件定義書・API仕様書 | クライアント |
| 実装完了 | YYYY-MM-DD | 動作するアプリケーション | PM |
| UAT完了 | YYYY-MM-DD | テスト結果・検収書 | クライアント |
| 最終納品 | YYYY-MM-DD | 全納品物 | クライアント |

## バッファ管理
| フェーズ | 予定工期 | バッファ | 理由 |
|---------|---------|---------|------|
| 設計 | | 10% | 要件の深掘り |
| 実装 | | 20% | 技術的不確実性 |
| テスト | | 30% | バグ修正・UAT対応 |

## リスクと対応
| リスク | 発生確率 | 影響度 | 対応策 |
|-------|---------|-------|-------|
| 要件変更 | 中 | 高 | 変更管理プロセスで対応 |
| 技術的困難 | 低 | 中 | スパイク（調査）タスクを前倒し |
| クライアント承認遅延 | 中 | 高 | 事前に期限を合意 |
