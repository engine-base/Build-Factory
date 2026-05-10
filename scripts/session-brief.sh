#!/bin/bash
# Build-Factory セッション開始ブリーフィング
#
# .claude/settings.json の SessionStart hook から呼ばれる。
# 起動時に「現状 + 次のタスク + 必読リスト」を stderr に表示し、
# Claude が即座に文脈を把握 → ユーザーは「進めて」と言うだけで実装着手可能。
#
# 手動実行: bash scripts/session-brief.sh

cd "$(dirname "$0")/.."

# stderr に出力 (Claude Code の SessionStart hook は stderr をコンテキストに入れる)
{
echo ""
echo "============================================================"
echo "📋 Build-Factory セッション開始 ($(date +%Y-%m-%d))"
echo "============================================================"
echo ""

echo "🌿 ブランチ: $(git branch --show-current 2>/dev/null || echo '?')"
echo "📌 直近コミット: $(git log -1 --oneline 2>/dev/null || echo '?')"
echo ""

# タスク状況サマリー
echo "📊 タスク状況:"
python3 scripts/validate-tickets.py 2>&1 | grep -E "Total tickets|Compliant tickets" | sed 's/^/   /'

# クリティカルパス先頭の未着手タスク
echo ""
echo "🎯 次に着手すべきタスク (クリティカルパス先頭):"
python3 - <<'PY' 2>/dev/null
import json
try:
    d = json.load(open('docs/task-decomposition/2026-05-09_v1/tickets.json'))
    crit = d.get('critical_path', [])
    tickets = {t['id']: t for t in d['tickets']}
    for tid in crit:
        if tid not in tickets:
            continue
        t = tickets[tid]
        # ここでは status フィールドが無いので、最初の critical を出す
        # 将来 status='done' で skip する分岐を追加可能
        print(f"   → {tid}")
        print(f"      title  : {t.get('title', '?')}")
        print(f"      label  : {t.get('label')} | sprint: {t.get('sprint')} | feature: {t.get('feature')}")
        if t.get('mock_link'):
            print(f"      mock   : {t['mock_link']}")
        if t.get('spec_link'):
            print(f"      spec   : {t['spec_link']}")
        ac = t.get('acceptance_criteria', [])
        print(f"      AC     : {len(ac)} 件 (EARS)")
        break
    else:
        print("   (クリティカルパスなし)")
except Exception as e:
    print(f"   (タスク取得失敗: {e})")
PY

echo ""
echo "📚 必読 (この順で):"
echo "   1. CLAUDE.md (このファイル経由で自動読み込み済み)"
echo "   2. docs/HANDOVER.md (全成果物の統合インデックス)"
echo "   3. docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md (実装 7 ステップ SOP)"
echo ""

echo "🛠 機械的強制レイヤー (動作中):"
echo "   - PostToolUse hook    : 編集後の絵文字混入を即警告"
echo "   - PostToolUse hook    : git commit/push 前に lint 推奨、--no-verify/--force 警告"
echo "   - permissions.deny    : git push --force / --no-verify は機械的に拒否"
echo "   - scripts/lint-mock.sh: 絵文字 / AGPL / ARCHIVE 残留 / メタ検証 (CI で fail)"
echo ""

echo "💡 次の指示例:"
echo "   ・「次のタスクを進めて」      → クリティカルパス先頭から実装着手"
echo "   ・「T-XXX を実装して」         → 指定タスクを IMPLEMENTATION_PROTOCOL の 7 ステップで実装"
echo "   ・「現状を確認して」           → bash scripts/lint-mock.sh + validate-tickets.py 実行"
echo "   ・「PR を作って」              → 実装完了タスクを GitHub PR 化"
echo ""
echo "============================================================"
echo ""
} >&2
