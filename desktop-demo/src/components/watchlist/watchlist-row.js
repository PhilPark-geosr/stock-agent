(() => {
function WatchlistRow(stock, selectedSymbol, onSelect, onDelete) {
  const row = document.createElement("div");
  row.className = `watchlist-row${stock.symbol === selectedSymbol ? " active" : ""}`;

  const selectButton = document.createElement("button");
  selectButton.type = "button";
  selectButton.className = "watchlist-item";
  const label = document.createElement("span");
  label.className = "stock-label";
  const symbol = document.createElement("strong");
  symbol.textContent = stock.symbol;
  const name = document.createElement("small");
  name.textContent = stock.name;
  label.append(symbol, name);
  const alert = document.createElement("span");
  alert.className = "stock-alert";
  alert.textContent = stock.alertStatus;
  selectButton.append(label, alert);
  selectButton.addEventListener("click", () => onSelect(stock.symbol));

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "watchlist-remove";
  deleteButton.setAttribute("aria-label", `${stock.symbol} 관심종목 삭제`);
  deleteButton.textContent = "×";
  deleteButton.addEventListener("click", () => onDelete(stock.symbol));

  row.append(selectButton, deleteButton);
  return row;
}

window.StockAgent = { ...window.StockAgent, WatchlistRow };
})();
