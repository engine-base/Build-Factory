"""
register_design_assets.py — data/design-systems と data/skills を skill_definitions に登録

Build-Factory の管理 UI / AI 社員 が参照できるように DB に登録する。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def register():
    import aiosqlite
    from db.queries import DB_PATH

    BF_ROOT = Path(__file__).resolve().parents[2]
    SKILLS_DIR = BF_ROOT / "data" / "skills"
    DESIGN_DIR = BF_ROOT / "data" / "design-systems"

    inserted_skills = 0
    inserted_designs = 0

    async with aiosqlite.connect(DB_PATH) as db:
        # ── skills ──
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            skill_name = skill_dir.name

            # 既存確認
            cur = await db.execute(
                "SELECT id FROM skill_definitions WHERE skill_name = ?", (skill_name,)
            )
            row = await cur.fetchone()
            if row:
                continue

            text = skill_md.read_text(encoding="utf-8", errors="ignore")
            # description を frontmatter から抽出（簡易）
            desc = ""
            if text.startswith("---"):
                end = text.find("---", 4)
                if end > 0:
                    fm = text[4:end]
                    for line in fm.splitlines():
                        if line.strip().startswith("description:"):
                            d = line.split(":", 1)[1].strip().strip("|").strip()
                            if d:
                                desc = d
                                break
                            # block scalar - 次の行から取る
                            continue
                        if desc == "" and line.startswith("  "):
                            desc = line.strip()
                            break
            desc = desc[:200] if desc else f"Open Design 由来のスキル: {skill_name}"

            await db.execute(
                """INSERT INTO skill_definitions
                   (skill_name, display_name, description, category, tags, md_path)
                   VALUES (?, ?, ?, 'design', '#open-design,#design', ?)""",
                (skill_name, skill_name, desc, str(skill_md)),
            )
            inserted_skills += 1

        await db.commit()

        # ── design-systems を knowledge_base に登録 ──
        # （DESIGN.md は「ブランド指針」として retrieval 対象にする）
        for design_dir in sorted(DESIGN_DIR.iterdir()):
            if not design_dir.is_dir() or design_dir.name.startswith("_"):
                continue
            design_md = design_dir / "DESIGN.md"
            if not design_md.exists():
                continue
            design_name = design_dir.name

            cur = await db.execute(
                "SELECT id FROM knowledge_base "
                "WHERE title = ? AND category = 'design-system'",
                (design_name,),
            )
            row = await cur.fetchone()
            if row:
                continue

            text = design_md.read_text(encoding="utf-8", errors="ignore")
            await db.execute(
                """INSERT INTO knowledge_base
                   (title, content, summary, category, tags, source, md_path)
                   VALUES (?, ?, ?, 'design-system', ?, 'open-design', ?)""",
                (
                    design_name, text[:50000], text[:300],
                    f"#open-design,#design-system,#{design_name}",
                    str(design_md),
                ),
            )
            inserted_designs += 1

        await db.commit()

    print(f"[register] skills:         {inserted_skills} 件投入 (skill_definitions)")
    print(f"[register] design-systems: {inserted_designs} 件投入 (knowledge_base, category='design-system')")


if __name__ == "__main__":
    asyncio.run(register())
