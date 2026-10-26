(() => {
const { WatchlistRow } = window.StockAgent;

function WatchlistPanel() {
  return `
    <aside id="watchlist-section" class="watchlist-card card">
      <div class="section-heading">
        <div><h2>관심종목</h2><p>관심 있는 종목을 등록한 뒤 분석하거나 브리핑에 담아보세요.</p></div>
        <span id="watchlist-count"></span>
      </div>
      <div id="watchlist" class="watchlist"></div>
      <form id="add-symbol-form" class="add-symbol-form">
        <div id="catalog-security-picker"></div>
        <p>미연결 관심종목은 위 검색에서 같은 종목을 선택해 연결하세요. 기존 조건과 기록을 유지합니다.</p>
        <button type="submit">관심종목 등록 · 연결</button>
      </form>
    </aside>`;
}

function renderWatchlist(stocks, selectedSymbol, onSelect, onDelete) {
  const list = document.querySelector("#watchlist");
  list.replaceChildren(...stocks.map((stock) => WatchlistRow(stock, selectedSymbol, onSelect, onDelete)));
  document.querySelector("#watchlist-count").textContent = `${stocks.length}개`;
}

window.StockAgent = { ...window.StockAgent, WatchlistPanel, renderWatchlist };
})();
