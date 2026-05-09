/* Build-Factory Mock — shared sidebar + header partials */

const SIDEBAR_HTML = (active = '') => `
  <a href="./index.html" class="sidebar-back">
    <i data-lucide="arrow-left" class="icon-sm"></i>
    モック一覧へ戻る
  </a>

  <div class="sidebar-project">
    <div class="sidebar-project-title">Build-Factory v1</div>
    <div class="sidebar-project-meta">
      <i data-lucide="building-2" class="icon-sm"></i>
      ●●株式会社
    </div>
    <div class="sidebar-project-progress"><span style="width:45%"></span></div>
    <div class="sidebar-project-meta" style="justify-content:space-between; margin-top:6px">
      <span>進捗 45%</span>
      <span>残 23 日</span>
    </div>
  </div>

  <div class="sidebar-section-title">プロジェクト管理</div>
  <a href="./workspace-home.html" class="sidebar-item ${active==='home'?'active':''}">
    <i data-lucide="layout-dashboard" class="icon"></i>
    ホーム
  </a>
  <a href="./progress.html" class="sidebar-item ${active==='progress'?'active':''}">
    <i data-lucide="trending-up" class="icon"></i>
    進捗管理
  </a>
  <a href="./tasks.html" class="sidebar-item ${active==='tasks'?'active':''}">
    <i data-lucide="check-square-2" class="icon"></i>
    タスク管理
    <span class="sidebar-item-badge">12</span>
  </a>
  <a href="./schedule.html" class="sidebar-item ${active==='schedule'?'active':''}">
    <i data-lucide="calendar" class="icon"></i>
    スケジュール
  </a>
  <a href="./minutes.html" class="sidebar-item ${active==='minutes'?'active':''}">
    <i data-lucide="file-text" class="icon"></i>
    議事録
  </a>
  <a href="./alerts.html" class="sidebar-item ${active==='alerts'?'active':''}">
    <i data-lucide="bell-ring" class="icon"></i>
    アラート / 質問
    <span class="sidebar-item-badge alert">5</span>
  </a>

  <div class="sidebar-section-title">開発フロー</div>
  <a href="#" class="sidebar-leader">
    <span class="leader-avatar leader-secretary">秘</span>
    秘書 AI
    <span class="sidebar-leader-status idle"></span>
  </a>
  <a href="./leader-pm.html" class="sidebar-leader ${active==='pm'?'active':''}" aria-expanded="${active==='pm'?'true':'false'}">
    <span class="leader-avatar leader-pm">PM</span>
    PM AI
    <span class="sidebar-leader-status"></span>
    <i data-lucide="chevron-${active==='pm'?'down':'right'}" class="icon-sm chevron"></i>
  </a>
  ${active==='pm' ? `
  <div class="sidebar-sub">
    <a href="#" class="sidebar-sub-item done"><span>ヒアリング</span><span class="sidebar-sub-status"><i data-lucide="check-circle-2" class="icon-sm"></i></span></a>
    <a href="#" class="sidebar-sub-item done"><span>要件定義</span><span class="sidebar-sub-status"><i data-lucide="check-circle-2" class="icon-sm"></i></span></a>
    <a href="#" class="sidebar-sub-item active"><span>提案・見積</span><span class="sidebar-sub-status"><i data-lucide="loader-2" class="icon-sm"></i></span></a>
    <a href="#" class="sidebar-sub-item"><span>受入条件</span><span class="sidebar-sub-status"><i data-lucide="circle-dot" class="icon-sm"></i></span></a>
  </div>
  ` : ''}
  <a href="#" class="sidebar-leader" aria-expanded="false">
    <span class="leader-avatar leader-arch">設</span>
    設計 AI
    <span class="sidebar-leader-status"></span>
    <i data-lucide="chevron-right" class="icon-sm chevron"></i>
  </a>
  <a href="#" class="sidebar-leader">
    <span class="leader-avatar leader-design">デ</span>
    デザイナー AI
    <span class="sidebar-leader-status"></span>
    <i data-lucide="chevron-right" class="icon-sm chevron"></i>
  </a>
  <a href="#" class="sidebar-leader">
    <span class="leader-avatar leader-eng">エ</span>
    エンジニア AI
    <span class="sidebar-leader-status idle"></span>
    <i data-lucide="chevron-right" class="icon-sm chevron"></i>
  </a>
  <a href="#" class="sidebar-leader">
    <span class="leader-avatar leader-qa">品</span>
    品質 AI
    <span class="sidebar-leader-status idle"></span>
    <i data-lucide="chevron-right" class="icon-sm chevron"></i>
  </a>
  <a href="#" class="sidebar-leader">
    <span class="leader-avatar leader-ops">運</span>
    DevOps AI
    <span class="sidebar-leader-status idle"></span>
    <i data-lucide="chevron-right" class="icon-sm chevron"></i>
  </a>

  <div class="sidebar-section-title">管理</div>
  <a href="./members.html" class="sidebar-item ${active==='members'?'active':''}">
    <i data-lucide="users" class="icon"></i>
    メンバー / 権限
  </a>
  <a href="#" class="sidebar-item">
    <i data-lucide="share-2" class="icon"></i>
    共有設定
  </a>
  <a href="./settings.html" class="sidebar-item ${active==='settings'?'active':''}">
    <i data-lucide="settings" class="icon"></i>
    プロジェクト設定
  </a>
`;

const HEADER_HTML = (currentPage = '') => `
  <div class="header-logo">
    <div class="header-logo-mark">BF</div>
    Build-Factory
  </div>
  <div class="header-divider"></div>
  <nav class="breadcrumb">
    <a href="./index.html">Workspaces</a>
    <i data-lucide="chevron-right" class="icon-sm"></i>
    <a href="./workspace-home.html">Build-Factory v1</a>
    ${currentPage ? `<i data-lucide="chevron-right" class="icon-sm"></i><span class="breadcrumb-current">${currentPage}</span>` : ''}
  </nav>
  <div class="header-spacer"></div>
  <button class="header-search">
    <i data-lucide="search" class="icon-sm"></i>
    検索 / コマンドパレット
    <span class="header-search-shortcut">⌘K</span>
  </button>
  <div class="header-actions">
    <button class="header-icon-btn" title="通知">
      <i data-lucide="bell" class="icon-lg"></i>
      <span class="badge-dot"></span>
    </button>
    <button class="header-icon-btn" title="ヘルプ">
      <i data-lucide="circle-help" class="icon-lg"></i>
    </button>
    <div class="header-avatar">MA</div>
  </div>
`;

function renderShell({ active = '', breadcrumb = '' } = {}) {
  const sidebar = document.querySelector('aside.sidebar');
  const header = document.querySelector('header.header');
  if (sidebar) sidebar.innerHTML = SIDEBAR_HTML(active);
  if (header) header.innerHTML = HEADER_HTML(breadcrumb);
  if (window.lucide) lucide.createIcons();
}
