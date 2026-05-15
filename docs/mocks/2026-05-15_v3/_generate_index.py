#!/usr/bin/env python3
"""Build-Factory v3 index.html generator.

機能:
- _screens.json から 64 画面の一覧を読む
- 各 category ディレクトリ配下の HTML mock を scan
- 存在する mock は <template> として embed
- 存在しない mock は "Coming Soon" placeholder
- 単一の自己完結 index.html を出力 (file 送付で全画面プレビュー可)

使い方:
    python3 docs/mocks/2026-05-15_v3/_generate_index.py
"""
import json
import html as html_escape
from pathlib import Path

V3_DIR = Path(__file__).parent
OUT = V3_DIR / "index.html"
SCREENS_JSON = V3_DIR / "_screens.json"

# Category dir mapping (slug → directory name relative to V3_DIR)
CATEGORY_DIR = {
    "auth": "auth",
    "account": "account",
    "workspace": "workspace",
    "moat-safety": "moat",
    "spec": "spec",
    "task-execution": "task",
    "review": "review",
    "ai-management": "ai",
    "knowledge-ops": "ops",
    "client": "client",
    "system": "system",
    "onboarding": "onboarding",
    "dialog": "dialog",
    "email": "email",
    "export": "export",
    "extras": "extras",
}


def find_mock_file(category_slug, screen_id, screen_name):
    """Locate a mock file for the given screen. Returns path str or None."""
    cat_dir = V3_DIR / CATEGORY_DIR.get(category_slug, category_slug)
    if not cat_dir.exists():
        return None
    # try common naming patterns
    candidates = [
        f"{screen_id}-{screen_name.replace('_', '-')}.html",
        f"{screen_id}-{screen_name}.html",
        f"{screen_id}.html",
    ]
    for c in candidates:
        p = cat_dir / c
        if p.exists():
            return p
    # fallback: glob for S-XXX-*
    for p in cat_dir.glob(f"{screen_id}-*.html"):
        return p
    return None


def main():
    with open(SCREENS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    categories = data["categories"]
    total = data["meta"]["total"]
    version = data["meta"]["version"]
    created = data["meta"]["created_at"]

    # Scan filesystem to determine done/todo per screen
    done_count = 0
    for cat in categories:
        for s in cat["screens"]:
            mock = find_mock_file(cat["id"], s["id"], s["name"])
            s["_file"] = str(mock.relative_to(V3_DIR)) if mock else None
            s["_status"] = "done" if mock else "todo"
            if mock:
                done_count += 1

    # Build sidebar HTML
    sidebar_items = []
    for cat in categories:
        cat_done = sum(1 for s in cat["screens"] if s["_status"] == "done")
        cat_total = len(cat["screens"])
        sidebar_items.append(f'''
        <div class="cat-group" data-cat-id="{cat['id']}">
          <button class="cat-header" onclick="toggleCat('{cat['id']}')">
            <i data-lucide="{cat['icon']}" class="w-3.5 h-3.5"></i>
            <span class="cat-label">{html_escape.escape(cat['label'])}</span>
            <span class="cat-count">{cat_done}/{cat_total}</span>
            <i data-lucide="chevron-down" class="w-3 h-3 cat-chevron"></i>
          </button>
          <div class="cat-screens">
        ''')
        for s in cat["screens"]:
            status_dot = "ok" if s["_status"] == "done" else "todo"
            screen_label = html_escape.escape(s.get("label", s["name"]))
            sidebar_items.append(f'''
            <button class="screen-item" data-screen-id="{s['id']}" data-file="{s['_file'] or ''}" onclick="loadScreen('{s['id']}')">
              <span class="status-dot status-{status_dot}"></span>
              <span class="screen-id mono">{s['id']}</span>
              <span class="screen-name">{screen_label}</span>
            </button>
            ''')
        sidebar_items.append("</div></div>")
    sidebar_html = "".join(sidebar_items)

    # Build embedded mock templates (use <script type="text/html"> for opaque storage)
    templates_html = []
    for cat in categories:
        for s in cat["screens"]:
            if s["_file"]:
                mock_path = V3_DIR / s["_file"]
                try:
                    content = mock_path.read_text(encoding="utf-8")
                except Exception as e:
                    print(f"⚠ failed to read {mock_path}: {e}")
                    continue
                # Escape </script> to prevent premature script termination
                content_safe = content.replace("</script>", "<\\/script>")
                templates_html.append(
                    f'<script type="text/html" id="mock-{s["id"]}">{content_safe}</script>'
                )

    # Final index.html
    out = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Build-Factory v3 — Mock Index ({done_count}/{total})</title>
<meta name="bf-doc-type" content="mock-index">
<meta name="bf-version" content="{version}">
<meta name="bf-total-screens" content="{total}">
<meta name="bf-done-count" content="{done_count}">

<script src="https://unpkg.com/lucide@latest"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Noto Sans JP', sans-serif;
    background: #f8fafc;
    color: #0f172a;
    line-height: 1.7;
    height: 100vh;
    overflow: hidden;
  }}
  .mono {{ font-family: 'JetBrains Mono', monospace; }}

  /* Top bar */
  .topbar {{
    height: 48px;
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    align-items: center;
    padding: 0 16px;
    gap: 12px;
  }}
  .brand {{ display: flex; align-items: center; gap: 8px; }}
  .brand-icon {{
    width: 24px; height: 24px;
    background: #1a6648;
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    color: #fff;
  }}
  .brand-title {{ font-size: 13px; font-weight: 700; }}
  .brand-meta {{ font-size: 11px; color: #64748b; font-family: 'JetBrains Mono', monospace; }}
  .progress-info {{ margin-left: auto; font-size: 11px; color: #475569; }}
  .progress-bar {{
    width: 120px; height: 4px;
    background: #e2e8f0;
    border-radius: 9999px;
    overflow: hidden;
    margin-left: 8px;
    display: inline-block;
    vertical-align: middle;
  }}
  .progress-fill {{
    height: 100%;
    background: #1a6648;
    border-radius: 9999px;
    width: {(done_count / total * 100):.0f}%;
  }}

  /* Layout */
  .container {{
    display: grid;
    grid-template-columns: 280px 1fr;
    height: calc(100vh - 48px);
  }}

  /* Sidebar */
  .sidebar {{
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
    overflow-y: auto;
    padding: 8px 0;
  }}
  .cat-group {{ border-bottom: 1px solid #f1f5f9; }}
  .cat-header {{
    width: 100%;
    background: transparent;
    border: none;
    padding: 8px 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #475569;
  }}
  .cat-header:hover {{ background: #f8fafc; }}
  .cat-label {{ flex: 1; text-align: left; }}
  .cat-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: #64748b;
    background: #f1f5f9;
    padding: 1px 6px;
    border-radius: 9999px;
    text-transform: none;
    letter-spacing: 0;
  }}
  .cat-chevron {{ transition: transform 0.15s; color: #94a3b8; }}
  .cat-group.collapsed .cat-chevron {{ transform: rotate(-90deg); }}
  .cat-group.collapsed .cat-screens {{ display: none; }}

  .cat-screens {{ padding: 2px 0 6px; }}
  .screen-item {{
    width: 100%;
    background: transparent;
    border: none;
    padding: 5px 14px 5px 28px;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-family: inherit;
    font-size: 12px;
    color: #475569;
    text-align: left;
  }}
  .screen-item:hover {{ background: #f8fafc; color: #0f172a; }}
  .screen-item.active {{ background: #f0faf5; color: #1a6648; font-weight: 600; }}
  .screen-item.active .screen-id {{ color: #1a6648; }}
  .status-dot {{
    width: 6px; height: 6px;
    border-radius: 9999px;
    flex-shrink: 0;
  }}
  .status-ok {{ background: #16a34a; }}
  .status-todo {{ background: #cbd5e1; }}
  .status-wip {{ background: #d97706; }}
  .screen-id {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: #94a3b8;
    width: 36px;
    flex-shrink: 0;
  }}
  .screen-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  /* Main preview */
  .main {{
    display: flex;
    flex-direction: column;
    background: #f8fafc;
  }}
  .preview-toolbar {{
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    height: 40px;
  }}
  .preview-info {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #475569;
  }}
  .preview-id {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #1a6648; font-weight: 600; }}
  .preview-meta {{ font-size: 11px; color: #94a3b8; margin-left: auto; }}
  .open-link {{
    font-size: 11px; color: #1a6648; text-decoration: none;
    padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px;
    display: inline-flex; align-items: center; gap: 4px;
  }}
  .open-link:hover {{ background: #f0faf5; }}

  .preview-frame {{
    flex: 1;
    border: none;
    width: 100%;
    background: #ffffff;
  }}

  .empty-state {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #94a3b8;
    text-align: center;
    padding: 32px;
  }}
  .empty-state .icon-box {{
    width: 64px; height: 64px;
    border-radius: 12px;
    background: #f1f5f9;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 16px;
  }}
  .empty-state h3 {{ font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 4px; }}
  .empty-state p {{ font-size: 13px; color: #64748b; }}
</style>
</head>
<body>

<header class="topbar">
  <div class="brand">
    <div class="brand-icon"><i data-lucide="factory" class="w-3.5 h-3.5"></i></div>
    <span class="brand-title">Build-Factory</span>
    <span class="brand-meta">v3 Mock Index</span>
  </div>
  <div class="progress-info">
    Progress: <strong>{done_count}</strong> / {total}
    <span class="progress-bar"><span class="progress-fill"></span></span>
    {(done_count/total*100):.0f}%
  </div>
</header>

<div class="container">
  <aside class="sidebar">
    {sidebar_html}
  </aside>

  <main class="main">
    <div class="preview-toolbar">
      <div class="preview-info" id="preview-info">
        <span style="color:#94a3b8;">←</span> 左から画面を選んでください
      </div>
      <a id="preview-open-link" class="open-link" style="display:none;" target="_blank" rel="noopener">
        <i data-lucide="external-link" class="w-3 h-3"></i>新しいタブで開く
      </a>
    </div>
    <iframe id="preview-frame" class="preview-frame" style="display:none;"></iframe>
    <div id="empty-state" class="empty-state">
      <div class="icon-box"><i data-lucide="layout" class="w-7 h-7" style="color:#64748b;"></i></div>
      <h3>画面を選んでプレビュー</h3>
      <p>左のサイドバーから画面 ID を選択すると、ここにモックが表示されます。</p>
    </div>
  </main>
</div>

<!-- Embedded mock templates -->
{"".join(templates_html)}

<script>
  lucide.createIcons();

  function toggleCat(catId) {{
    const cat = document.querySelector('[data-cat-id="' + catId + '"]');
    cat.classList.toggle('collapsed');
  }}

  function loadScreen(screenId) {{
    // Highlight active
    document.querySelectorAll('.screen-item').forEach(el => el.classList.remove('active'));
    const activeEl = document.querySelector('[data-screen-id="' + screenId + '"]');
    activeEl?.classList.add('active');

    const template = document.getElementById('mock-' + screenId);
    const frame = document.getElementById('preview-frame');
    const empty = document.getElementById('empty-state');
    const info = document.getElementById('preview-info');
    const openLink = document.getElementById('preview-open-link');

    const file = activeEl?.getAttribute('data-file') || '';
    const screenLabel = activeEl?.querySelector('.screen-name')?.textContent || '';

    if (template) {{
      // script type=text/html stores raw text. Unescape escaped close tags.
      // NOTE: literal close tag is built via concat to avoid premature HTML parser termination.
      const content = template.textContent.split('<\\\\/script>').join('</' + 'script>');
      frame.srcdoc = content;
      frame.style.display = 'block';
      empty.style.display = 'none';
      info.innerHTML = '<span class="preview-id">' + screenId + '</span>' +
        '<span style="color:#cbd5e1;">·</span>' +
        '<span>' + screenLabel + '</span>';
      if (file) {{
        openLink.href = file;
        openLink.style.display = 'inline-flex';
      }} else {{
        openLink.style.display = 'none';
      }}
    }} else {{
      frame.style.display = 'none';
      empty.style.display = 'flex';
      empty.querySelector('h3').textContent = screenId + ' は未作成です';
      empty.querySelector('p').textContent = 'このモックはまだ生成されていません (ステータス: Todo)';
      info.innerHTML = '<span class="preview-id">' + screenId + '</span>' +
        '<span style="color:#cbd5e1;">·</span>' +
        '<span>' + screenLabel + '</span>' +
        '<span style="margin-left:8px; background:#f1f5f9; color:#64748b; font-size:10px; padding:1px 8px; border-radius:9999px; font-weight:600;">Todo</span>';
      openLink.style.display = 'none';
    }}
  }}

  // auto-open first done screen on load
  document.addEventListener('DOMContentLoaded', () => {{
    const firstDone = document.querySelector('.screen-item .status-ok');
    if (firstDone) {{
      const screenItem = firstDone.closest('.screen-item');
      const id = screenItem.getAttribute('data-screen-id');
      loadScreen(id);
    }}
  }});
</script>

</body>
</html>
'''
    OUT.write_text(out, encoding="utf-8")
    print(f"✓ wrote {OUT}")
    print(f"  total screens: {total}")
    print(f"  done (mock exists): {done_count}")
    print(f"  todo: {total - done_count}")
    print(f"  file size: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
