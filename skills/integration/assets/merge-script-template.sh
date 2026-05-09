#!/bin/bash
# 統合マージ実行スクリプト
# integration スキルの出力（マージ順序）に基づいて実行する
# 使用前に: git status でクリーンな状態を確認すること

set -e  # エラーで即停止

BASE_BRANCH="${1:-develop}"
DRY_RUN="${2:-false}"

echo "=== 統合マージスクリプト ==="
echo "ベースブランチ: $BASE_BRANCH"
echo "ドライラン: $DRY_RUN"
echo ""

# ブランチの最新化
echo "▶ ベースブランチを最新化..."
git fetch origin
git checkout "$BASE_BRANCH"
git pull origin "$BASE_BRANCH"

# マージ前チェック関数
check_ci_status() {
  local branch="$1"
  echo "  CIステータス確認: $branch"
  # gh run list --branch "$branch" --limit 1 で確認可能
  # ここでは手動確認を促す
  echo "  ⚠️  手動でCIがパスしていることを確認してください"
}

# マージ実行関数
merge_branch() {
  local branch="$1"
  local description="$2"

  echo ""
  echo "▶ マージ: $branch ($description)"

  if [ "$DRY_RUN" = "true" ]; then
    echo "  [DRY RUN] git merge --squash $branch"
    echo "  [DRY RUN] git commit -m 'feat: $description'"
    return
  fi

  # プレビュー（コンフリクト確認）
  git merge --no-commit --no-ff "$branch" 2>/dev/null || {
    echo "  ⚠️  コンフリクト発生! 手動解決が必要です"
    git merge --abort 2>/dev/null || true
    echo "  解決後、手動でマージしてください: git merge $branch"
    exit 1
  }

  # コンフリクトなければ実際にマージ
  git merge --abort 2>/dev/null || true
  git merge --squash "$branch"
  git commit -m "feat: $description

Squash merge from $branch
Branch: $branch
" --no-edit || git commit -m "feat: $description (from $branch)"

  echo "  ✅ マージ完了: $branch"
}

# ===== マージ順序をここに定義 =====
# integration スキルの出力（STEP 1のマージ順序案）に基づいて編集する

echo "=== マージ開始 ==="

# check_ci_status "feature/auth"
# merge_branch "feature/auth" "認証機能の実装"

# check_ci_status "feature/data-model"
# merge_branch "feature/data-model" "データモデル・マイグレーション"

# check_ci_status "feature/core-api"
# merge_branch "feature/core-api" "コアAPI実装"

# check_ci_status "feature/frontend"
# merge_branch "feature/frontend" "フロントエンド実装"

echo ""
echo "=== 全マージ完了 ==="
echo "次のステップ:"
echo "  1. npm run build  # ビルド確認"
echo "  2. npm test       # テスト確認"
echo "  3. 動作確認後: git push origin $BASE_BRANCH"
