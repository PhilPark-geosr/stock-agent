(() => {
function WatchlistPanel() {
  return `
    <aside class="watchlist-card card">
      <div class="section-heading">
        <div><h2>관심종목</h2><p>API: GET /watchlist</p></div>
        <span id="watchlist-count"></span>
      </div>
      <div id="watchlist" class="watchlist"></div>
      <form id="add-symbol-form" class="add-symbol-form">
        <input id="add-symbol-input" placeholder="예: 005930.KS" aria-label="관심종목 추가">
        <button type="submit">POST /watchlist</button>
      </form>
    </aside>`;
}

function renderWatchlist(stocks, selectedSymbol, onSelect) {
  const list = document.querySelector("#watchlist");
  list.replaceChildren(...stocks.map((stock) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `watchlist-item${stock.symbol === selectedSymbol ? " active" : ""}`;
    button.innerHTML = `
      <span class="stock-label"><strong>${stock.symbol}</strong><small>${stock.name}</small></span>
      <span class="stock-alert">${stock.alertStatus}</span>`;
    button.addEventListener("click", () => onSelect(stock.symbol));
    return button;
  }));
  document.querySelector("#watchlist-count").textContent = `${stocks.length}개`;
}

window.StockAgent = { ...window.StockAgent, WatchlistPanel, renderWatchlist };
})();
