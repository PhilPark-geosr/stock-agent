(() => {
function WatchlistPanel() {
  return `
    <aside id="watchlist-section" class="watchlist-card card">
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

function renderWatchlist(stocks, selectedSymbol, onSelect, onDelete) {
  const list = document.querySelector("#watchlist");
  list.replaceChildren(...stocks.map((stock) => {
    const row = document.createElement("div");
    row.className = `watchlist-row${stock.symbol === selectedSymbol ? " active" : ""}`;
    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "watchlist-item";
    selectButton.innerHTML = `
      <span class="stock-label"><strong>${stock.symbol}</strong><small>${stock.name}</small></span>
      <span class="stock-alert">${stock.alertStatus}</span>`;
    selectButton.addEventListener("click", () => onSelect(stock.symbol));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "watchlist-remove";
    deleteButton.setAttribute("aria-label", `${stock.symbol} 관심종목 삭제`);
    deleteButton.textContent = "×";
    deleteButton.addEventListener("click", () => onDelete(stock.symbol));
    row.append(selectButton, deleteButton);
    return row;
  }));
  document.querySelector("#watchlist-count").textContent = `${stocks.length}개`;
}

window.StockAgent = { ...window.StockAgent, WatchlistPanel, renderWatchlist };
})();
