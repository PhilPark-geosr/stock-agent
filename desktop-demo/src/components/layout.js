(() => {
function Sidebar() {
  return `
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32"><path d="M7 20l6-7 5 4 8-10"/><path d="M21 7h5v5"/></svg>
        </span>
        <span><strong>STOCK AGENT</strong><small>OFFLINE DEMO</small></span>
      </div>
      <nav class="flow-nav" aria-label="데모 흐름">
        <span class="flow-step active">1. 관심종목 선택</span>
        <span class="flow-step">2. 최신 분석 확인</span>
        <span class="flow-step">3. 이력 비교</span>
        <span class="flow-step">4. 알림 상태 확인</span>
      </nav>
      <div class="demo-notice">
        <div><span class="status-dot"></span><strong>MOCK MODE</strong></div>
        <p>FastAPI, SQLite, Gemini, yfinance, Kakao API와 연결하지 않은 화면 검증용 앱입니다.</p>
      </div>
    </aside>`;
}

function Topbar() {
  return `
    <header class="topbar">
      <div>
        <p class="eyebrow">ANALYSIS DASHBOARD</p>
        <h1>관심종목 분석 데모</h1>
        <p class="subtitle">현재 구현된 기능을 기준으로 관심종목, 최신 분석, 분석 이력, 카카오 알림 상태를 확인합니다.</p>
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
