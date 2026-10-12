(() => {
const { AccountMenu } = window.StockAgent;

function Topbar() {
  return `
    <header class="topbar">
      <div>
        <p class="eyebrow">ANALYSIS DASHBOARD</p>
        <h1>관심종목 분석</h1>
        <p class="subtitle">관심종목의 흐름을 살펴보고, 나에게 필요한 분석과 브리핑을 확인하세요.</p>
      </div>
      <div class="topbar-actions">
        <button id="notification-connection-button" class="secondary-button" data-connected="false" type="button">카카오 알림 연결</button>
        <form id="search-form" class="search-form" role="search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg>
          <input id="search-input" autocomplete="off" placeholder="관심종목 코드 검색" aria-label="관심종목 검색">
        </form>
        <button id="run-analysis-button" class="primary-button" type="button">수동 분석 실행</button>
        ${AccountMenu()}
      </div>
    </header>`;
}

window.StockAgent = { ...window.StockAgent, Topbar };
})();
