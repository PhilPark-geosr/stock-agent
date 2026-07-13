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

window.StockAgent = { ...window.StockAgent, Sidebar };
})();
