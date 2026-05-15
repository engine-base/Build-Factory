# Phase 1 Dogfood セットアップガイド

> **対象**: ENGINE BASE 内製 dogfood (Phase 1) を即着手するためのオペレーション手順
> **作成日**: 2026-05-14
> **前提**: Phase 9 実装完走 (187/187 task done) / Phase 10 着手中

---

## 0. ゴール (受入基準)

1 案件を Build-Factory 上で end-to-end 通せる:

```
workspace 作成 → AI 社員召喚 → ヒアリング (Mary)
  → 要件定義 (Preston) → アーキ設計 (Winston) → 機能分解 (Sally)
  → タスク分解 (Devon) → 実装 → Review (Quinn) → 納品
```

成功定義: **1 つの真の案件** を 1 セッションで進められること。

---

## 1. クラウド契約 (¥0/月)

### Supabase Free (DB / Auth / Storage)

1. https://supabase.com/ で account 作成 (GitHub OAuth で OK)
2. New Project → region: ap-northeast-1 (Tokyo) / Database password 設定
3. 取得する 4 vars:
   - `SUPABASE_URL` (Project Settings → API → Project URL)
   - `SUPABASE_PUBLISHABLE_KEY` (旧 anon key)
   - `SUPABASE_SECRET_KEY` (旧 service_role key)
   - `SUPABASE_DB_URL` (Database → Connection string → URI format)

### Vercel Hobby (Frontend)

1. https://vercel.com/ で account 作成 (GitHub OAuth)
2. New Project → Import `engine-base/Build-Factory` → root `frontend/`
3. Environment Variables 設定:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
   - `NEXT_PUBLIC_API_URL` (= Oracle Cloud Backend URL)

### Oracle Cloud Free Tier (Backend / 永久無料 4 vCPU + 24GB RAM)

1. https://cloud.oracle.com/ で account 作成 (クレカ要登録だが課金 0)
2. Compute → Create Instance:
   - Shape: Ampere A1 (Always Free)
   - OS: Ubuntu 22.04
   - 1 OCPU / 6GB RAM (= 4 つまで作れる)
3. SSH key 設定, public IP 取得
4. Cloudflare Tunnel で HTTPS 化 (https://www.cloudflare.com/products/tunnel/)

---

## 2. ローカル → 本番展開

### Step 1: Supabase migrations 適用

```bash
# Supabase CLI install
brew install supabase/tap/supabase  # or scoop on Windows

# project link
cd Build-Factory
supabase link --project-ref <YOUR-PROJECT-REF>

# 全 13 migrations 適用
supabase db push
```

確認: Supabase Dashboard → Database → Tables で 50+ table が出現。

### Step 2: Backend デプロイ (Oracle Cloud)

```bash
# Oracle Cloud VM に ssh
ssh ubuntu@<your-oracle-ip>

# repo clone + Python install
git clone https://github.com/engine-base/Build-Factory.git
cd Build-Factory/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env 配置 (Supabase 4 vars + ANTHROPIC_API_KEY 等)
cp .env.example .env
nano .env  # 編集

# 起動 (systemd or pm2)
DISABLE_BACKGROUND_WORKERS=0 uvicorn main:app --host 0.0.0.0 --port 8001
```

ヘルスチェック: `curl http://<oracle-ip>:8001/api/health`

### Step 3: Cloudflare Tunnel

```bash
# Oracle VM 上で
cloudflared tunnel login
cloudflared tunnel create build-factory-api
cloudflared tunnel route dns build-factory-api api.yourdomain.com
cloudflared tunnel run --url http://localhost:8001 build-factory-api
```

### Step 4: Vercel デプロイ

Vercel Dashboard で auto deploy が動く。`NEXT_PUBLIC_API_URL` を Step 3 の `https://api.yourdomain.com` に設定。

---

## 3. dogfood 受入テスト (手動 1 案件通し)

### シナリオ A: 認証 + workspace 作成
- [ ] サインアップ / ログイン
- [ ] workspace 作成 (Slice S1)
- [ ] AI 社員 (BMAD 10 persona) が表示される

### シナリオ B: ヒアリング → 要件定義
- [ ] Mary (BA) と会話してヒアリング (Slice S3)
- [ ] Preston (PM) が要件定義書を出す

### シナリオ C: アーキ → 分解 → タスク化
- [ ] Winston (Architect) で ER 図生成 (Slice S4)
- [ ] Sally (PO) で機能分解
- [ ] Devon (Dev) でタスク分解

### シナリオ D: Kanban / DAG / Phase
- [ ] タスク Kanban で進捗管理 (Slice S5)
- [ ] DAG で依存可視化
- [ ] Cmd+K で横断検索

### シナリオ E: Swarm 並列実行
- [ ] 4 並列 cell で並列実装 (Slice S7)
- [ ] worktree 隔離 + file_lock 動作

### シナリオ F: 配信
- [ ] PR 自動作成 (Slice S8)
- [ ] Slack 通知
- [ ] Obsidian エクスポート

---

## 4. 既知の制約 / 妥協点

### Phase 9 完走時点での既知事項

| | 状況 |
|---|---|
| Frontend e2e (Playwright) | UI は Python static-validation のみ。Phase 2 で追加予定。 |
| DB 実接続 integration test | SQL 静的解析中心。Supabase 立てた後に通し test 必要。 |
| Generic AC 56 件 | EARS compliant だが内容 generic。Phase 2 公開前に retrofit 推奨。 |
| Post-hoc audit MD 116 件 | test PASS だが AC 個別 mapping 浅め。重要部から pre-flight format に retrofit。 |

### Phase 1 dogfood で意図的にスコープ外

- 自社以外への提供 (= Phase 2 で SaaS 公開)
- 課金 / ToS / SLA
- 1 社で 10 案件超え時の負荷 (= scale-up は Oracle Cloud upgrade で対応)

---

## 5. トラブルシューティング

### `pip install -r requirements.txt` で claude-agent-sdk が入らない

→ Python 3.11.5 以上必須。

### Supabase migrations が conflict

→ `supabase db reset` (注意: 全 data 消える)。Phase 1 では構わない。

### Cloudflare Tunnel が繋がらない

→ Oracle Cloud の VCN security list で port 8001 を internal で開放。

---

## 6. 完了後の動き

dogfood で 1 案件を完走したら:

1. **HANDOVER.md / CLAUDE.md** を「Phase 9 + Phase 10 完走」に更新
2. **Phase 2 計画** 着手 (公開 SaaS 化, 課金, ToS, 監視, SLA)
3. **学び (= dogfood で見つかった bug / UX 改善)** を tickets-v2 に follow-up task として追加

---

## 7. 緊急 contact / 参照

- CLAUDE.md §11 質問・判断保留時の動き
- `docs/decisions/` (ADR 12 件)
- `docs/REVIEW_REPORT_2026-05-14.md` (Phase 9 完走レビュー)

---

_Author: Claude Code (with masato) / Date: 2026-05-14_
