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
        <input id="add-symbol-input" placeholder="예: 005930.KS" aria-label="관심종목 추가">
        <button type="submit">관심종목 추가</button>
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
