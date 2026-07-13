(() => {
const { state, errorMessage } = window.StockAgent;

function createWatchlistController({ backend, renderScreen, showToast, showView, loadSelectedAnalysis }) {
  async function loadWatchlist() {
    const items = await backend.listWatchlist();
    state.stocks = items.map((item) => ({
      ...item,
      name: item.symbol,
      alertStatus: item.symbol === state.selectedSymbol ? "불러오는 중" : "분석 대기"
    }));
    if (!state.stocks.some((stock) => stock.symbol === state.selectedSymbol)) {
      state.selectedSymbol = state.stocks[0]?.symbol || null;
    }
    if (state.selectedSymbol) {
      await loadSelectedAnalysis();
    } else {
      state.selectedAnalysis = null;
      state.analysisHistory = [];
      renderScreen();
    }
  }

  async function selectStock(symbol) {
    state.selectedSymbol = symbol;
    state.selectedAnalysis = null;
    state.analysisHistory = [];
    renderScreen();
    await loadSelectedAnalysis();
    showView("analysis-view");
  }

  async function deleteWatchlistItem(symbol) {
    try {
      await backend.deleteWatchlist(symbol);
      showToast(`${symbol}을 관심종목에서 삭제했습니다.`);
      await loadWatchlist();
    } catch (error) {
      showToast(`관심종목 삭제 실패: ${errorMessage(error)}`);
    }
  }

  function bindWatchlistEvents() {
    document.querySelector("#search-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = document.querySelector("#search-input");
      const query = input.value.trim().toUpperCase();
      const match = state.stocks.find((stock) => stock.symbol.includes(query) || stock.name.toUpperCase().includes(query));
      if (!query || !match) {
        showToast("관심종목에서 일치하는 종목을 찾지 못했습니다.");
        return;
      }
      input.value = "";
      await selectStock(match.symbol);
    });

    document.querySelector("#add-symbol-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = document.querySelector("#add-symbol-input");
      const rawSymbol = input.value.trim().toUpperCase();
      if (!rawSymbol) {
        showToast("추가할 종목 코드를 입력하세요.");
        return;
      }
      const symbol = rawSymbol.includes(".") ? rawSymbol : `${rawSymbol}.KS`;
      try {
        await backend.addWatchlist(symbol);
        state.selectedSymbol = symbol;
        input.value = "";
        showToast(`${symbol}을 관심종목에 추가했습니다.`);
        await loadWatchlist();
      } catch (error) {
        showToast(`관심종목 추가 실패: ${errorMessage(error)}`);
      }
    });
  }

  return { bindWatchlistEvents, deleteWatchlistItem, loadWatchlist, selectStock };
}

window.StockAgent = { ...window.StockAgent, createWatchlistController };
})();
