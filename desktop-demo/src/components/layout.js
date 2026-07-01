(() => {
function Sidebar() {
  return `
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32"><path d="M7 20l6-7 5 4 8-10"/><path d="M21 7h5v5"/></svg>
        </span>
        <span><strong>STOCK AGENT</strong><small>DESKTOP CLIENT</small></span>
      </div>
      <nav class="flow-nav" aria-label="주요 화면">
        <button class="flow-step active" type="button" data-view="watchlist-view">1. 관심종목 선택</button>
        <button class="flow-step" type="button" data-view="analysis-view">2. 최신 분석 확인</button>
        <button class="flow-step" type="button" data-view="history-view">3. 이력 비교</button>
        <button class="flow-step" type="button" data-view="alerts-view">4. 알림 상태 확인</button>
      </nav>
      <div class="demo-notice">
        <div><span class="status-dot"></span><strong id="backend-connection">BACKEND 연결 중</strong></div>
        <p id="backend-detail">로컬 FastAPI 상태를 확인하고 있습니다.</p>
      </div>
    </aside>`;
}

function Topbar() {
  return `
    <header class="topbar">
      <div>
        <p class="eyebrow">ANALYSIS DASHBOARD</p>
        <h1>관심종목 분석</h1>
        <p class="subtitle">FastAPI와 연결된 관심종목, 최신 분석, 분석 이력, 사용자 알림 조건을 관리합니다.</p>
      </div>
      <div class="topbar-actions">
        <form id="search-form" class="search-form" role="search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg>
          <input id="search-input" autocomplete="off" placeholder="005930.KS 또는 삼성전자" aria-label="관심종목 검색">
        </form>
        <button id="run-analysis-button" class="primary-button" type="button">수동 분석 실행</button>
      </div>
    </header>`;
}

function AppShell(content) {
  return `
    <div class="app-frame">
      ${Sidebar()}
      <main class="main-content">
        ${Topbar()}
        ${content}
      </main>
    </div>
    <div id="toast" class="toast" role="status" aria-live="polite"></div>`;
}

window.StockAgent = { ...window.StockAgent, AppShell };
})();
