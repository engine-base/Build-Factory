"""
skill_manager.py — スキル CRUD + 評価 + パッケージング (チャット・Slack・MCP 共通バックエンド)

スキル保存先:
  primary:  <repo>/data/skills/<name>/
  mirror:   ~/.claude/skills/<name>/  (Claude desktop からも見えるように)

両方に同期して保存。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

SKILL_STORE = Path(__file__).resolve().parents[2] / "data" / "skills"
# ~/.claude/skills へのミラーは Build-Factory 専用サブディレクトリに分離
# （company-dashboard と衝突しないように）
_default_mirror = Path.home() / ".claude" / "skills" / "build-factory"
CLAUDE_SKILLS = Path(os.environ.get("CLAUDE_SKILLS_MIRROR") or _default_mirror)
SKILL_CREATOR_PATH = SKILL_STORE / "skill-creator"
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"


# ──────────────────────────────────────────
# skill_definitions テーブル同期（管理 UI 連携）
# ──────────────────────────────────────────

async def register_skill_in_db(name: str, description: str, md_path: str,
                                category: str = "custom") -> None:
    """skill_definitions テーブルに upsert する（管理 UI が参照する）。"""
    from db import async_db as aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM skill_definitions WHERE skill_name=?", (name,)
        )
        row = await cur.fetchone()
        if row:
            await db.execute(
                """UPDATE skill_definitions
                   SET description=?, md_path=?, category=?, is_active=1,
                       updated_at=datetime('now','localtime')
                   WHERE skill_name=?""",
                (description, md_path, category, name),
            )
        else:
            await db.execute(
                """INSERT INTO skill_definitions
                   (skill_name, display_name, description, category, md_path, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (name, name, description, category, md_path),
            )
        await db.commit()


async def sync_filesystem_to_db() -> dict:
    """ファイルシステムの全スキル → skill_definitions に同期。
    UI に表示されない問題を解消する。"""
    skills = await list_skills()
    registered = 0
    for s in skills:
        try:
            md_path = str(Path(s["path"]) / "SKILL.md")
            # category 推測（既存ロジックがあれば優先）
            category = "custom"
            name = s["name"]
            if name in ("staff-management", "skill-creator"):
                category = "system"
            elif name.startswith("0"):
                category = "department"
            await register_skill_in_db(
                name=s["name"], description=s["description"],
                md_path=md_path, category=category,
            )
            registered += 1
        except Exception as e:
            print(f"[skill_manager.sync] {s['name']}: {e}")
    return {"registered": registered, "total": len(skills)}


# ──────────────────────────────────────────
# ヘルパー
# ──────────────────────────────────────────

def _both_paths(name: str) -> tuple[Path, Path]:
    return SKILL_STORE / name, CLAUDE_SKILLS / name


def _parse_frontmatter(skill_md: str) -> tuple[dict, str]:
    """SKILL.md を frontmatter dict と body に分解。"""
    if not skill_md.startswith("---\n"):
        return {}, skill_md
    end = skill_md.find("\n---\n", 4)
    if end == -1:
        return {}, skill_md
    fm_text = skill_md[4:end]
    body = skill_md[end + 5:]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        fm = {}
    return fm, body


# ──────────────────────────────────────────
# 一覧 / 取得
# ──────────────────────────────────────────

async def list_skills() -> list[dict]:
    """SKILL_STORE の全スキルを {name, description, path} で返す。"""
    out: list[dict] = []
    if not SKILL_STORE.exists():
        return out
    for d in sorted(SKILL_STORE.iterdir()):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, _ = _parse_frontmatter(text)
        out.append({
            "name": fm.get("name") or d.name,
            "description": (fm.get("description") or "").strip(),
            "path": str(d),
            "has_scripts": (d / "scripts").is_dir(),
            "has_references": (d / "references").is_dir(),
            "has_evals": (d / "evals").is_dir() or (d / "evals.json").exists(),
        })
    return out


async def get_skill(name: str) -> Optional[dict]:
    """特定スキルの SKILL.md とディレクトリ情報を返す。"""
    p = SKILL_STORE / name
    if not p.is_dir():
        return None
    skill_md = p / "SKILL.md"
    if not skill_md.exists():
        return None
    text = skill_md.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    files = []
    for f in p.rglob("*"):
        if f.is_file() and not any(part.startswith(".") for part in f.relative_to(p).parts):
            files.append(str(f.relative_to(p)))
    return {
        "name": fm.get("name") or name,
        "description": fm.get("description") or "",
        "frontmatter": fm,
        "body": body,
        "skill_md_full": text,
        "files": sorted(files),
        "path": str(p),
    }


# ──────────────────────────────────────────
# 作成 / 更新
# ──────────────────────────────────────────

async def create_skill(
    name: str,
    description: str,
    body: str,
    *,
    overwrite: bool = False,
) -> dict:
    """新規スキルを作成。primary + mirror 両方に書く。"""
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("name は英数字 + ハイフン/アンダースコアのみ")
    primary, mirror = _both_paths(name)
    if primary.exists() and not overwrite:
        raise ValueError(f"スキル '{name}' は既に存在します（overwrite=true で上書き）")

    primary.mkdir(parents=True, exist_ok=True)
    fm_yaml = yaml.safe_dump(
        {"name": name, "description": description.strip()},
        allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    skill_md = f"---\n{fm_yaml}---\n\n{body.strip()}\n"
    (primary / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # 推奨サブディレクトリ
    for sub in ("scripts", "references", "assets", "evals"):
        (primary / sub).mkdir(exist_ok=True)

    # ミラー
    if mirror.exists():
        shutil.rmtree(mirror)
    shutil.copytree(primary, mirror)

    # 管理 UI に出るよう DB 登録
    try:
        await register_skill_in_db(
            name=name, description=description.strip(),
            md_path=str(primary / "SKILL.md"), category="custom",
        )
    except Exception as e:
        print(f"[create_skill] DB 登録失敗: {e}")

    return {"name": name, "path": str(primary), "mirror": str(mirror)}


async def update_skill_md(name: str, new_skill_md: str) -> dict:
    """SKILL.md 全体を上書き。primary + mirror + skill_definitions すべてに反映。"""
    primary, mirror = _both_paths(name)
    if not primary.is_dir():
        raise FileNotFoundError(f"スキル '{name}' が存在しない")
    (primary / "SKILL.md").write_text(new_skill_md, encoding="utf-8")
    mirror.mkdir(parents=True, exist_ok=True)
    (mirror / "SKILL.md").write_text(new_skill_md, encoding="utf-8")

    # skill_definitions テーブル同期（description が変わっていても追従）
    fm, _ = _parse_frontmatter(new_skill_md)
    new_desc = (fm.get("description") or "").strip()
    if new_desc:
        try:
            await register_skill_in_db(
                name=name, description=new_desc,
                md_path=str(primary / "SKILL.md"), category="custom",
            )
        except Exception as e:
            print(f"[update_skill_md] DB sync 失敗: {e}")
    return {"name": name, "updated": True}


async def update_description(name: str, new_description: str) -> dict:
    """description だけ書き換え（最適化結果の適用用）。"""
    cur = await get_skill(name)
    if not cur:
        raise FileNotFoundError(f"スキル '{name}' が無い")
    fm = dict(cur["frontmatter"])
    fm["description"] = new_description.strip()
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    new_md = f"---\n{fm_yaml}---\n\n{cur['body'].lstrip()}"
    return await update_skill_md(name, new_md)


async def delete_skill(name: str, *, hard: bool = False) -> dict:
    """スキル削除。
    既定 (hard=False): ファイルは残し DB を is_active=0 にする（リバート可能・既存挙動と一致）
    hard=True: primary + mirror + DB レコードも完全削除
    """
    from db import async_db as aiosqlite
    primary, mirror = _both_paths(name)

    if hard:
        if primary.is_dir(): shutil.rmtree(primary)
        if mirror.is_dir():  shutil.rmtree(mirror)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM skill_definitions WHERE skill_name=?", (name,)
            )
            await db.commit()
        return {"name": name, "deleted": True, "hard": True}

    # soft delete（既存 routers/skills.py と挙動を揃える）
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE skill_definitions SET is_active=0, "
            "updated_at=datetime('now','localtime') WHERE skill_name=?",
            (name,),
        )
        await db.commit()
    return {"name": name, "deleted": True, "hard": False, "files_kept": True}


# ──────────────────────────────────────────
# T-002-02: archive / restore
# ──────────────────────────────────────────

# archive 先: data/skills/_archive/<name>/<timestamp>/
SKILL_ARCHIVE = SKILL_STORE / "_archive"


class SkillNotFoundError(Exception):
    """archive 対象スキルが skill_definitions に存在しない."""


class SkillAlreadyArchivedError(Exception):
    """既に archive 済みのスキルを再 archive しようとした."""


async def archive_skill(
    name: str,
    *,
    actor_user_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    """スキルを archive する (T-002-02 REFACTOR).

    - SKILL.md と eval を data/skills/_archive/<name>/<timestamp>/ に move
    - skill_definitions.is_active = 0, version = 'archived'
    - mirror (~/.claude/skills) からも削除
    - 既存 delete_skill(soft) の上位互換: archive_reason を保存 + 物理 move
    """
    from db import async_db as aiosqlite
    from datetime import datetime

    primary, mirror = _both_paths(name)
    if not primary.is_dir():
        raise SkillNotFoundError(f"skill not found on disk: {name}")

    # DB 存在確認
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, is_active, version FROM skill_definitions WHERE skill_name=?",
            (name,),
        )
        if not rows:
            raise SkillNotFoundError(f"skill not found in DB: {name}")
        row = dict(rows[0])
        if row.get("version") == "archived":
            raise SkillAlreadyArchivedError(f"skill {name!r} already archived")

    # 1. archive directory 準備
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive_dir = SKILL_ARCHIVE / name / ts
    archive_dir.parent.mkdir(parents=True, exist_ok=True)

    # 2. primary を archive へ move
    shutil.move(str(primary), str(archive_dir))

    # 3. mirror は削除
    if mirror.is_dir():
        shutil.rmtree(mirror)

    # 4. archive メタデータ JSON
    meta = {
        "skill_name": name,
        "archived_at": ts,
        "actor_user_id": actor_user_id,
        "reason": reason,
    }
    (archive_dir / "_archive_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 5. DB 更新 (is_active=0 + version='archived')
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE skill_definitions SET is_active=0, version='archived', "
            "updated_at=datetime('now','localtime') WHERE skill_name=?",
            (name,),
        )
        await db.commit()

    return {
        "name": name,
        "archived": True,
        "archive_dir": str(archive_dir),
        "archived_at": ts,
        "reason": reason,
    }


async def restore_skill(
    name: str,
    *,
    actor_user_id: Optional[str] = None,
    archived_at: Optional[str] = None,
) -> dict:
    """archive から restore (最新 archive を default).

    - data/skills/_archive/<name>/<latest>/ → data/skills/<name>/ に move
    - skill_definitions.is_active = 1, version = '1.0' に戻す
    - mirror も再生成
    """
    from db import async_db as aiosqlite

    primary, mirror = _both_paths(name)
    archive_root = SKILL_ARCHIVE / name
    if not archive_root.is_dir():
        raise SkillNotFoundError(f"no archive found for {name!r}")

    # 既に active が存在する場合は restore しない (重複防止)
    if primary.is_dir():
        raise SkillAlreadyArchivedError(f"active skill already exists: {name}")

    # 復元対象の timestamp dir を決定
    versions = sorted([p for p in archive_root.iterdir() if p.is_dir()], reverse=True)
    if not versions:
        raise SkillNotFoundError(f"no archive versions for {name!r}")
    if archived_at:
        target = archive_root / archived_at
        if not target.is_dir():
            raise SkillNotFoundError(f"archive version not found: {archived_at}")
    else:
        target = versions[0]

    # move back to primary
    primary.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(primary))

    # mirror 再生成
    try:
        mirror.parent.mkdir(parents=True, exist_ok=True)
        if mirror.is_dir():
            shutil.rmtree(mirror)
        shutil.copytree(primary, mirror)
    except Exception:
        pass

    # DB 更新
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE skill_definitions SET is_active=1, version='1.0', "
            "updated_at=datetime('now','localtime') WHERE skill_name=?",
            (name,),
        )
        await db.commit()

    return {
        "name": name,
        "restored": True,
        "restored_from": target.name,
        "actor_user_id": actor_user_id,
    }


async def list_archived_skills() -> list[dict]:
    """archive 済みスキル一覧 (DB の version='archived' 行)."""
    from db import async_db as aiosqlite

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, skill_name, display_name, category, updated_at "
            "FROM skill_definitions WHERE version='archived' "
            "ORDER BY updated_at DESC"
        )
    return [dict(r) for r in rows]


# ──────────────────────────────────────────
# テストケース
# ──────────────────────────────────────────

async def add_eval(name: str, prompt: str, expected: str = "", files: Optional[list[str]] = None) -> dict:
    primary = SKILL_STORE / name
    if not primary.is_dir():
        raise FileNotFoundError(name)
    evals_dir = primary / "evals"
    evals_dir.mkdir(exist_ok=True)
    evals_json = evals_dir / "evals.json"
    data = {"skill_name": name, "evals": []}
    if evals_json.exists():
        try:
            data = json.loads(evals_json.read_text(encoding="utf-8"))
        except Exception:
            pass
    next_id = (max([e.get("id", 0) for e in data["evals"]] or [0])) + 1
    data["evals"].append({
        "id": next_id, "prompt": prompt,
        "expected_output": expected, "files": files or [],
    })
    evals_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"name": name, "eval_id": next_id, "total": len(data["evals"])}


async def list_evals(name: str) -> list[dict]:
    p = SKILL_STORE / name / "evals" / "evals.json"
    if not p.exists():
        return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")) or {}).get("evals") or []
    except Exception:
        return []


# ──────────────────────────────────────────
# パッケージ
# ──────────────────────────────────────────

async def package_skill(name: str) -> dict:
    """skill-creator の package_skill.py を呼ぶ。"""
    primary = SKILL_STORE / name
    if not primary.is_dir():
        raise FileNotFoundError(name)
    pkg_script = SKILL_CREATOR_PATH / "scripts" / "package_skill.py"
    if not pkg_script.exists():
        raise FileNotFoundError(f"package_skill.py が見つからない: {pkg_script}")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(pkg_script), str(primary),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output_path = primary.parent / f"{name}.skill"
    return {
        "name": name,
        "skill_file": str(output_path) if output_path.exists() else None,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "ok": proc.returncode == 0,
    }


# ──────────────────────────────────────────
# テスト実行（簡易版・サブエージェント無し環境向け）
# ──────────────────────────────────────────

async def run_eval_inline(name: str, eval_id: int, *,
                          provider: str = "openai", model: str = "gpt-4o-mini") -> dict:
    """1つのテストケースを LLM に投げて出力をワークスペースに保存する。"""
    skill = await get_skill(name)
    if not skill:
        raise FileNotFoundError(name)
    evals = await list_evals(name)
    target = next((e for e in evals if e.get("id") == eval_id), None)
    if not target:
        raise ValueError(f"eval id {eval_id} 無し")

    workspace = SKILL_STORE.parent / f"{name}-workspace" / "iteration-1" / f"eval-{eval_id}"
    ws = workspace / "with_skill" / "outputs"
    ws.mkdir(parents=True, exist_ok=True)

    # メタデータ保存
    (workspace / "eval_metadata.json").write_text(
        json.dumps({"eval_id": eval_id, "prompt": target["prompt"], "assertions": []},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # SKILL.md + プロンプトを LLM に投げる
    from llm.config import get_openai_client, LLMProvider
    try:
        client = get_openai_client(LLMProvider(provider), {})
    except ValueError:
        client = get_openai_client(LLMProvider.OPENAI, {})
    import time, os as _os
    if not _os.environ.get("OPENAI_API_KEY") and provider == "openai":
        return {"error": "OPENAI_API_KEY 未設定", "eval_id": eval_id}

    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "あなたは以下のスキルに従って業務を行います:\n\n" + skill["skill_md_full"]},
                {"role": "user", "content": target["prompt"]},
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        tokens = (getattr(usage, "total_tokens", 0) if usage else 0) or 0
    except Exception as e:
        return {"error": str(e), "eval_id": eval_id}
    dur_ms = int((time.time() - t0) * 1000)

    (ws / "output.md").write_text(text, encoding="utf-8")
    (workspace / "with_skill" / "timing.json").write_text(
        json.dumps({"total_tokens": tokens, "duration_ms": dur_ms,
                    "total_duration_seconds": round(dur_ms / 1000, 1)},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "eval_id": eval_id,
        "workspace": str(workspace),
        "output_chars": len(text),
        "tokens": tokens,
        "duration_seconds": round(dur_ms / 1000, 1),
        "preview": text[:500],
    }
