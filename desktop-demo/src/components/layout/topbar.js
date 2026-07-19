(() => {
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

window.StockAgent = { ...window.StockAgent, Topbar };
})();
