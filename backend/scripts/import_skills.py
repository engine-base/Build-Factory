"""
import_skills.py — 既存 .skill ファイルを新しい格納場所にインポートする

使い方:
  python backend/scripts/import_skills.py

.skill ファイル（ZIPアーカイブ）を展開し
  <repo>/data/skills/{skill_name}/SKILL.md に保存、
  skill_definitions テーブルにメタデータを登録する。
"""

import re
import sqlite3
import zipfile
from pathlib import Path

SKILL_ZIP_DIR = Path.home() / "Documents" / "skills"
SKILL_STORE   = Path(__file__).resolve().parents[2] / "data" / "skills"
DB_PATH       = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

# タブ → カテゴリ マッピング
TAB_TO_CATEGORY = {
    "財務・経理": "finance",
    "営業・集客": "sales",
    "マーケティング": "marketing",
    "Web・コンテンツ": "content",
    "ブランディング": "marketing",
    "顧客・CRM": "cs",
    "カスタマーサクセス": "cs",
    "CS・サポート": "cs",
    "人事・採用": "hr",
    "総務・法務": "admin",
    "法務・契約": "admin",
    "バックオフィス": "admin",
    "外注管理": "admin",
    "経営戦略": "strategy",
    "戦略・定義": "strategy",
    "経営・戦略": "strategy",
    "目標・管理": "strategy",
    "設計": "design",
    "実装・分解": "tech",
    "開発・技術": "tech",
    "品質・運用": "ops",
    "リスク管理": "ops",
    "ネットワーク": "ops",
    "プロジェクト": "project",
    "分析・調査": "analytics",
    "情報・ナレッジ": "knowledge",
    "その他": "general",
    "総括": "general",
}


def parse_frontmatter(text: str) -> dict:
    """SKILL.md の YAML フロントマターを簡易パースする。"""
    meta = {}
    # 最初の --- ... --- ブロックを抽出
    m = re.search(r'^---\s*\n(.*?)\n---', text, re.DOTALL | re.MULTILINE)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ':' in line:
            key, _, val = line.partition(':')
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta


def import_skill(skill_zip: Path, db: sqlite3.Connection) -> bool:
    skill_name = skill_zip.stem  # ファイル名（拡張子なし）

    try:
        with zipfile.ZipFile(skill_zip, 'r') as zf:
            # SKILL.md を探す
            skill_md_path = None
            for name in zf.namelist():
                if name.endswith('SKILL.md') and not name.startswith('__MACOSX'):
                    skill_md_path = name
                    break

            if not skill_md_path:
                print(f"  [WARN] SKILL.md が見つかりません: {skill_zip.name}")
                return False

            content = zf.read(skill_md_path).decode('utf-8')

    except Exception as e:
        print(f"  [FAIL] ZIP展開失敗 {skill_zip.name}: {e}")
        return False

    # フロントマター解析
    meta = parse_frontmatter(content)
    display_name = meta.get('name', skill_name)
    description  = meta.get('description', '')
    tab          = meta.get('tab', '')
    category     = TAB_TO_CATEGORY.get(tab, 'general')

    # タグを skill_name から推定（フロントマターにない場合）
    tags = f"#{skill_name}"
    if tab:
        tags += f", #{tab}"

    # 格納先ディレクトリ作成
    dest_dir = SKILL_STORE / skill_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "SKILL.md"
    dest_file.write_text(content, encoding='utf-8')

    # DB 登録（既存なら UPDATE）
    db.execute("""
        INSERT INTO skill_definitions
          (skill_name, display_name, description, category, tags, md_path, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(skill_name) DO UPDATE SET
          display_name = excluded.display_name,
          description  = excluded.description,
          category     = excluded.category,
          tags         = excluded.tags,
          md_path      = excluded.md_path,
          updated_at   = datetime('now','localtime')
    """, (skill_name, display_name, description[:500], category, tags, str(dest_file)))

    return True


def main():
    if not SKILL_ZIP_DIR.exists():
        print(f"[FAIL] スキルフォルダが見つかりません: {SKILL_ZIP_DIR}")
        return

    skill_files = list(SKILL_ZIP_DIR.glob("*.skill"))
    if not skill_files:
        print("[WARN] .skill ファイルが見つかりません")
        return

    print(f"[INFO] {len(skill_files)}個の .skill ファイルをインポートします")
    print(f"   → 格納先: {SKILL_STORE}")
    print()

    db = sqlite3.connect(DB_PATH)
    ok = fail = 0

    for sf in sorted(skill_files):
        success = import_skill(sf, db)
        if success:
            print(f"  [OK] {sf.stem}")
            ok += 1
        else:
            fail += 1

    db.commit()
    db.close()

    print()
    print(f"完了: 成功 {ok}件 / 失敗 {fail}件")
    print(f"格納先: {SKILL_STORE}")


if __name__ == "__main__":
    main()
