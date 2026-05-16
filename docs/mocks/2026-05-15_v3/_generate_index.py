#!/usr/bin/env python3
"""Build-Factory v3 index.html generator (simple navigation approach).

シンプル: 各 mock = 独立 HTML / index.html の各項目は <a href> で直接遷移する。
- iframe / base64 / srcdoc 一切なし
- ブラウザの戻るボタンで index に戻れる
- 各 mock にも「← Index に戻る」フローティングボタン付与
"""
import json
import html as html_escape
from pathlib import Path

V3_DIR = Path(__file__).parent
OUT = V3_DIR / "index.html"
SCREENS_JSON = V3_DIR / "_screens.json"

CATEGORY_DIR = {
    "auth": "auth", "account": "account", "workspace": "workspace",
    "moat-safety": "moat", "spec": "spec", "task-execution": "task",
    "review": "review", "ai-management": "ai", "knowledge-ops": "ops",
    "client": "client", "system": "system", "onboarding": "onboarding",
    "dialog": "dialog", "email": "email", "export": "export", "extras": "extras",
}


def find_mock_file(category_slug, screen_id, screen_name):
    cat_dir = V3_DIR / CATEGORY_DIR.get(category_slug, category_slug)
    if not cat_dir.exists():
        return None
    candidates = [
        f"{screen_id}-{screen_name.replace('_', '-')}.html",
        f"{screen_id}-{screen_name}.html",
        f"{screen_id}.html",
    ]
    for c in candidates:
        p = cat_dir / c
        if p.exists():
            return p
    for p in cat_dir.glob(f"{screen_id}-*.html"):
        return p
    return None


def main():
    with open(SCREENS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    categories = data["categories"]
    total = data["meta"]["total"]
    version = data["meta"]["version"]

    done_count = 0
    for cat in categories:
        for s in cat["screens"]:
            mock = find_mock_file(cat["id"], s["id"], s["name"])
            s["_file"] = str(mock.relative_to(V3_DIR)) if mock else None
            s["_status"] = "done" if mock else "todo"
            if mock:
                done_count += 1

    # Build categories HTML (cards instead of sidebar)
    cat_sections = []
    for cat in categories:
        cat_done = sum(1 for s in cat["screens"] if s["_status"] == "done")
        cat_total = len(cat["screens"])
        cat_sections.append(f'''
    <section class="cat-section">
      <header class="cat-header">
        <div class="cat-title">
          <i data-lucide="{cat['icon']}" class="w-4 h-4"></i>
          <span>{html_escape.escape(cat['label'])}</span>
        </div>
        <span class="cat-count">{cat_done}/{cat_total}</span>
      </header>
      <div class="screen-grid">''')
        for s in cat["screens"]:
            status = s["_status"]
            screen_label = html_escape.escape(s.get("label", s["name"]))
            if s["_file"]:
                cat_sections.append(f'''
        <a class="screen-card screen-done" href="{s['_file']}">
          <div class="screen-card-head">
            <span class="status-dot status-ok"></span>
            <span class="screen-id">{s['id']}</span>
          </div>
          <div class="screen-card-name">{screen_label}</div>
          <div class="screen-card-cta">
            <span>開く</span>
            <i data-lucide="arrow-right" class="w-3 h-3"></i>
          </div>
        </a>''')
            else:
                cat_sections.append(f'''
        <div class="screen-card screen-todo">
          <div class="screen-card-head">
            <span class="status-dot status-todo"></span>
            <span class="screen-id">{s['id']}</span>
          </div>
          <div class="screen-card-name">{screen_label}</div>
          <div class="screen-card-cta cta-todo">
            <span>Todo</span>
          </div>
        </div>''')
        cat_sections.append("</div></section>")
    cat_html = "".join(cat_sections)

    progress_pct = (done_count / total * 100) if total else 0

    out = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Build-Factory v3 — Mock Index ({done_count}/{total})</title>
<meta name="bf-doc-type" content="mock-index">
<meta name="bf-version" content="{version}">

<script src="https://unpkg.com/lucide@latest"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Noto Sans JP', sans-serif;
    background: #f8fafc; color: #0f172a;
    line-height: 1.7;
    min-height: 100vh;
  }}
  .mono {{ font-family: 'JetBrains Mono', monospace; }}

  .topbar {{
    background: #fff;
    border-bottom: 1px solid #e2e8f0;
    padding: 12px 16px;
    position: sticky; top: 0; z-index: 10;
  }}
  .topbar-inner {{
    max-width: 1400px; margin: 0 auto;
    display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap;
  }}
  .brand {{ display: flex; align-items: center; gap: 8px; flex-shrink: 0; }}
  .brand-icon {{
    width: 28px; height: 28px; background: #1a6648;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    color: #fff;
  }}
  .brand-title {{ font-size: 14px; font-weight: 700; }}
  .brand-meta {{ font-size: 11px; color: #64748b; font-family: 'JetBrains Mono', monospace; }}

  .progress {{
    margin-left: auto;
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; color: #475569;
  }}
  .progress strong {{ font-size: 14px; color: #0f172a; font-family: 'JetBrains Mono', monospace; }}
  .progress-bar {{
    width: 120px; height: 6px;
    background: #e2e8f0; border-radius: 9999px;
    overflow: hidden;
  }}
  .progress-fill {{
    height: 100%; background: #1a6648;
    border-radius: 9999px;
    width: {progress_pct:.0f}%;
    transition: width 0.3s;
  }}

  .container {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px 16px 64px;
  }}

  .intro {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 24px;
  }}
  .intro h1 {{
    font-size: 20px; font-weight: 700;
    margin-bottom: 6px;
  }}
  .intro p {{
    font-size: 13px; color: #475569;
    line-height: 1.7;
  }}
  .intro .legend {{
    display: flex; gap: 16px;
    margin-top: 12px;
    flex-wrap: wrap;
  }}
  .legend-item {{
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 12px; color: #475569;
  }}

  .cat-section {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-bottom: 16px;
    overflow: hidden;
  }}
  .cat-header {{
    padding: 12px 16px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    display: flex; align-items: center; gap: 8px;
  }}
  .cat-title {{
    display: flex; align-items: center; gap: 8px;
    flex: 1;
    font-size: 13px; font-weight: 700;
    color: #1a6648;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .cat-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: #64748b;
    background: #fff;
    border: 1px solid #e2e8f0;
    padding: 2px 8px;
    border-radius: 9999px;
  }}

  .screen-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 8px;
    padding: 12px;
  }}

  .screen-card {{
    display: flex; flex-direction: column;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 12px;
    text-decoration: none;
    color: inherit;
    transition: all 0.15s;
    min-height: 90px;
  }}
  .screen-card.screen-done:hover {{
    border-color: #1a6648;
    background: #f0faf5;
    transform: translateY(-1px);
  }}
  .screen-card.screen-todo {{
    background: #f8fafc;
    border-style: dashed;
    cursor: default;
    opacity: 0.7;
  }}
  .screen-card-head {{
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 6px;
  }}
  .status-dot {{
    width: 6px; height: 6px;
    border-radius: 9999px;
    flex-shrink: 0;
  }}
  .status-ok {{ background: #16a34a; }}
  .status-todo {{ background: #cbd5e1; }}
  .screen-id {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: #64748b;
    font-weight: 600;
  }}
  .screen-card-name {{
    font-size: 14px; font-weight: 600;
    color: #0f172a;
    line-height: 1.4;
    margin-bottom: auto;
    padding-bottom: 8px;
  }}
  .screen-todo .screen-card-name {{ color: #64748b; }}
  .screen-card-cta {{
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 12px;
    color: #1a6648;
    font-weight: 600;
    margin-top: 8px;
  }}
  .cta-todo {{
    color: #94a3b8;
    background: #f1f5f9;
    padding: 2px 8px;
    border-radius: 9999px;
    font-weight: 600;
    font-size: 10px;
    align-self: flex-start;
    margin-top: 4px;
  }}

  @media (max-width: 640px) {{
    .container {{ padding: 16px 12px 48px; }}
    .topbar {{ padding: 10px 12px; }}
    .brand-meta {{ display: none; }}
    .progress {{ width: 100%; order: 3; }}
    .progress-bar {{ flex: 1; width: auto; }}
    .screen-grid {{ grid-template-columns: 1fr; gap: 8px; padding: 10px; }}
    .screen-card {{ min-height: auto; padding: 10px; }}
  }}
</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <div class="brand-icon"><i data-lucide="factory" class="w-3.5 h-3.5"></i></div>
      <span class="brand-title">Build-Factory</span>
      <span class="brand-meta">v3 Mock Index</span>
    </div>
    <div class="progress">
      <strong>{done_count}</strong>
      <span style="color:#cbd5e1;">/</span>
      <span>{total}</span>
      <span class="progress-bar"><span class="progress-fill"></span></span>
      <span class="mono" style="font-size:11px; color:#64748b;">{progress_pct:.0f}%</span>
    </div>
  </div>
</header>

<div class="container">
  <div class="intro">
    <h1>v3 Mock 一覧 ({done_count}/{total})</h1>
    <p>
      Build-Factory v3 のデザイン基盤に基づいた全画面モックの一覧です。
      <strong>Done</strong> (緑) のカードをタップ / クリックすると個別の mock 画面に遷移します。
      ブラウザの戻るボタンでこの一覧に戻れます。
    </p>
    <div class="legend">
      <span class="legend-item"><span class="status-dot status-ok"></span>Done = 作成済み (タップで遷移)</span>
      <span class="legend-item"><span class="status-dot status-todo"></span>Todo = 未作成</span>
    </div>
  </div>

  {cat_html}
</div>

<script>
  lucide.createIcons();
</script>
</body>
</html>
'''
    OUT.write_text(out, encoding="utf-8")
    print(f"[OK] wrote {OUT}")
    print(f"  total screens: {total}")
    print(f"  done (mock exists): {done_count}")
    print(f"  todo: {total - done_count}")
    print(f"  file size: {OUT.stat().st_size:,} bytes")
    print(f"  approach: simple <a href> navigation (no iframe)")


if __name__ == "__main__":
    main()
