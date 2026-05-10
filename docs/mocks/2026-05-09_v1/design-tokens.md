# Build-Factory Design Tokens v1.0

全モック HTML が共通参照する **Tailwind ベースのデザイントークン**。

## 1. Color Palette（ENGINE BASE 緑基調）

### Brand
| Token | Hex | 用途 |
|---|---|---|
| `--bf-primary` | `#1a6648` | メインブランド緑（headers / CTA / accents）|
| `--bf-primary-hover` | `#155236` | hover 状態 |
| `--bf-primary-light` | `#e6f4ee` | 薄い緑（badges / active states）|
| `--bf-primary-border` | `#b3d9c8` | 緑系 border |

### Semantic
| Token | Hex | 用途 |
|---|---|---|
| `--bf-success` | `#16a34a` | 成功 / passed |
| `--bf-warning` | `#f59e0b` | 警告 / blocked / 仮説 |
| `--bf-danger` | `#dc2626` | 失敗 / 赤線 / unwanted |
| `--bf-info` | `#3b82f6` | 情報 |

### Neutral
| Token | Hex | 用途 |
|---|---|---|
| `--bf-bg-page` | `#f0f2f5` | ページ背景 |
| `--bf-bg-card` | `#ffffff` | カード背景 |
| `--bf-bg-subtle` | `#f8fafc` | 薄いセクション背景 |
| `--bf-border` | `#e2e8f0` | 標準 border |
| `--bf-text-primary` | `#1a1a1a` | メイン文字 |
| `--bf-text-secondary` | `#475569` | セカンダリ文字 |
| `--bf-text-muted` | `#94a3b8` | 補助文字 |

### Status badges
| Status | Background | Text | Border |
|---|---|---|---|
| Triage | `#f1f5f9` | `#475569` | `#cbd5e1` |
| Todo | `#dbeafe` | `#1e40af` | `#bfdbfe` |
| Ready | `#fef3c7` | `#92400e` | `#fde68a` |
| In Progress | `#e0e7ff` | `#4338ca` | `#c7d2fe` |
| Blocked | `#fee2e2` | `#991b1b` | `#fecaca` |
| Done | `#dcfce7` | `#166534` | `#86efac` |

## 2. Typography（Noto Sans JP）

```html
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700;900&display=swap" rel="stylesheet">
```

| Token | Size | Weight | 用途 |
|---|---|---|---|
| `text-display` | 28-36px | 900 | ページタイトル |
| `text-h1` | 22-24px | 700 | セクションヘッダー |
| `text-h2` | 16-18px | 700 | サブヘッダー |
| `text-h3` | 14px | 700 | 小見出し |
| `text-body` | 13-14px | 400 | 本文 |
| `text-small` | 12-13px | 400 | 補助 |
| `text-caption` | 10-11px | 600 | UPPERCASE label |

`font-feature-settings: "palt"` で日本語の prop spacing を最適化。

## 3. Spacing scale（Tailwind 4 base = 4px）

| Token | Value | 用途 |
|---|---|---|
| `--space-1` | 4px | 微小 |
| `--space-2` | 8px | inline gap |
| `--space-3` | 12px | small gap |
| `--space-4` | 16px | standard gap |
| `--space-6` | 24px | section gap |
| `--space-8` | 32px | large gap |
| `--space-12` | 48px | hero gap |

## 4. Border radius

| Token | Value | 用途 |
|---|---|---|
| `rounded-sm` | 3px | badges |
| `rounded-md` | 6px | inputs / small cards |
| `rounded-lg` | 8px | section cards |
| `rounded-xl` | 12px | hero cards |
| `rounded-full` | 9999px | pills / avatars |

## 5. Shadow

| Token | 用途 |
|---|---|
| `shadow-sm` | カード（標準）|
| `shadow-md` | hover 時 |
| `shadow-lg` | modal / popover |

```css
shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
shadow-md: 0 4px 12px rgba(0,0,0,0.08);
shadow-lg: 0 10px 30px rgba(0,0,0,0.12);
```

## 6. Layout patterns

### App Shell（標準）

```
┌─────────────────────────────────────────┐
│ Sidebar (230px) │ Main (max-w-1080px)    │
│ - Logo          │ - Top bar (账号 menu)   │
│ - Navigation    │ - Content              │
│ - Footer        │                        │
└─────────────────────────────────────────┘
```

### Sidebar（ENGINE BASE 緑 / 固定）

```html
<aside class="w-[230px] h-screen fixed bg-[#1a6648] text-white">
  <!-- Logo + version -->
  <div class="p-5 border-b border-white/10">...</div>
  <!-- Nav links -->
  <nav class="py-2.5">
    <a class="flex px-4.5 py-1.5 text-white/65 hover:bg-white/7 hover:text-white border-l-2 border-transparent hover:border-white/30">...</a>
    <a class="active border-l-2 border-[#00c97a] bg-white/10 text-white">...</a>
  </nav>
</aside>
```

### Card（標準）

```html
<div class="bg-white rounded-lg p-7 shadow-sm border border-[#e2e8f0]">
  <h2 class="text-base font-bold text-[#1a6648] pb-3 mb-5 border-b border-[#e2e8f0]">Title</h2>
  ...
</div>
```

## 7. Components 共通仕様

### Button

| Variant | Style |
|---|---|
| Primary | `bg-[#1a6648] text-white hover:bg-[#155236]` |
| Secondary | `bg-[#e6f4ee] text-[#1a6648] border border-[#b3d9c8] hover:bg-[#d1e9da]` |
| Ghost | `text-[#1a6648] hover:bg-[#f7fdf9]` |
| Danger | `bg-[#dc2626] text-white hover:bg-[#b91c1c]` |

Size: `text-xs px-3 py-1.5` (small) / `text-sm px-4 py-2` (md) / `text-base px-5 py-2.5` (lg)

### Input

```html
<input class="w-full px-3 py-2 text-sm border border-[#e2e8f0] rounded-md focus:border-[#1a6648] focus:ring-1 focus:ring-[#1a6648] outline-none">
```

### Badge

```html
<span class="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded-sm border bg-[#e6f4ee] text-[#1a6648] border-[#b3d9c8]">Active</span>
```

### Modal

```html
<div class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
  <div class="bg-white rounded-xl shadow-lg p-8 max-w-2xl w-full">
    <h3 class="text-lg font-bold text-[#1a6648] mb-4">Title</h3>
    ...
  </div>
</div>
```

### Toast

```html
<div class="fixed top-4 right-4 bg-white rounded-md shadow-lg border-l-4 border-[#16a34a] p-4 max-w-md">
  ...
</div>
```

## 8. Icons

採用: **Lucide Icons**（CDN）

```html
<script src="https://unpkg.com/lucide@latest"></script>
<script>lucide.createIcons();</script>
<i data-lucide="play"></i>
```

主要アイコン: `play`, `pause`, `check`, `x`, `chevron-right`, `users`, `settings`, `bell`, `search`, `git-branch`, `flag`, `alert-triangle`, `bot`, `code`, `file-text`, `globe`

## 9. Accessibility

- WCAG 2.1 AA 準拠
- 全 interactive 要素に `aria-label` / `role`
- コントラスト比 4.5:1 以上
- キーボードナビ可（`Tab` / `Cmd+K` で global search）
- focus 状態は明示（`ring-2 ring-[#1a6648]/50`）

## 10. Responsive

| Breakpoint | Width | Phase |
|---|---|---|
| Mobile (default) | <768px | Phase 3 で対応 |
| md: | 768px+ | **Phase 1 メインターゲット** |
| lg: | 1024px+ | デスクトップ最適 |
| xl: | 1280px+ | wide |

Phase 1 = `md:` 以上で完璧動作・モバイルは「動くがレイアウト崩れる」許容。

## 11. Mermaid for diagrams

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({
  startOnLoad: true,
  theme: 'base',
  themeVariables: {
    primaryColor: '#1a6648',
    primaryTextColor: '#fff',
    lineColor: '#1a6648',
    fontFamily: 'Noto Sans JP'
  }
});
</script>
```

## 12. Tailwind CDN（全モック共通）

```html
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        'bf-primary': '#1a6648',
        'bf-primary-hover': '#155236',
        'bf-primary-light': '#e6f4ee',
      }
    }
  }
}
</script>
```
