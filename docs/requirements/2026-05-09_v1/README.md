# Build-Factory v2.1 要件定義書 v1（2026-05-09）

このフォルダは **requirements-definition スキル STEP 6 の最終出力**を保管します。

> ヒアリング v2.1 → 要件定義書 v1 への昇格段階。次は architecture-design スキルへ。

---

## ファイル一覧

| ファイル | 役割 | 想定読者 |
|---|---|---|
| **`requirements-v1.html`** | クライアント提出用 要件定義書（HTML・ENGINE BASE 配色 / TOC サイドバー / Noto Sans JP） | クライアント / 監視担当 / 社内共有 |
| **`requirements-v1.md`** | Markdown サマリー（軽量編集用） | 開発者 / Git 差分管理 |
| **`requirements_internal.json`** | 内部用 JSON（機能要件・開発チーム向け）| Claude Code / 後続スキル入力 |
| **`requirements_decision_log.json`** | 判断ログ JSON（MCP 連携・データ蓄積） | 案件 DB / 次回類似案件高速化 |

---

## クイックビュー

### スコープ
- **Phase 1 Must = 30 項目**（M-1〜M-26 + M-5b + M-10a/b/c/d 内訳）
- **Phase 1.5 Should = 12 項目**（S-1〜S-12）
- **Phase 2 Could = 6 項目**（C-1〜C-5 + C-10）
- **Phase 3 Could = 4 項目**（C-6〜C-9）
- **Future = 1 項目**（C-11 個人クローン化サービス）
- **Won't = 8 項目**（W-1〜W-8）

### 前提
- ヒアリング v2.1（`docs/hearing/2026-05-09_re-hearing/`）の決定を全面継承
- 既存ユーザ移行なし（0 から構築 + テストデータ seed）
- 仕様書 + 画面モック HTML を画面・コンポーネント単位で自動生成
- AI 社員 3 階層（COO Phase 2 / 部署リーダー Phase 1.5 / メンバー Phase 1）+ 個人クローン素地

### 次のスキル
```
architecture-design → tech-stack → functional-breakdown
  → feature-decomposition → task-decomposition → distributed-dev
```

---

## 後続成果物

- 🆕 **architecture-design v1.0** → `docs/architecture/2026-05-09_v1/`
- 🆕 **functional-breakdown v1.0** → `docs/functional-breakdown/2026-05-09_v1/`
- 🆕 **feature-decomposition v1.0** → `docs/feature-decomposition/2026-05-09_v1/`（**Phase 1 Must = 34 に拡張**）
- 🆕 **tech-stack v1.0** → `docs/tech-stack/2026-05-09_v1/`（OSS / ライセンス / コスト確定）

## v1.1 反映予定（差分）

feature-decomposition / tech-stack で以下が追加・変更されました：
- **Phase 1 Must M-27 / M-28 / M-29 / M-30 追加**（30 → 34 項目）
  - M-27 Intent Router（LangGraph entry node）
  - M-28 Context Builder（Claude 流 3-tier compaction + prompt cache + 9-section summary）
  - M-29 Workspace Isolation = git worktree
  - M-30 Memory 3 層統合層（短期 / 中期 / 長期）
- **Phase 1.5 Should S-13 追加**：Real-time Session Steering（Codex CLI 参考）
- **Phase 2 Could C-12 / C-13 追加**：
  - C-12 Knowledge Graph（Apache AGE）
  - C-13 実装エンジン切替（Codex CLI / Gemini CLI）
- **M-12 強化**：OS-level sandbox（Seatbelt / Landlock + seccomp・Codex CLI 参考）
- **GrapesJS Studio SDK 不採用** → GrapesJS core（BSD-3・無料）
- **OpenAI Agents SDK 不採用** → LangGraph で代替

## 改訂履歴

- **v1.0**（2026-05-09）: ヒアリング v2.1 → 要件定義 v1 への正式昇格（30 Must）
- **v1.1 反映**（2026-05-09）: feature-decomposition / tech-stack で 34 Must / 13 Should / 13 Could に拡張（本フォルダの内容は v1.0 snapshot のまま保持・差分は後続フォルダ参照）
