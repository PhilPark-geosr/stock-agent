(() => {
const { state, errorMessage } = window.StockAgent;

function createWatchlistController({ backend, renderScreen, showToast, showView, loadSelectedAnalysis }) {
  async function loadWatchlist() {
    const items = await backend.listWatchlist();
    state.stocks = items.map((item) => ({
      ...item,
      name: item.security_name || item.symbol,
      alertStatus: item.alert_hold_reason || (item.symbol === state.selectedSymbol ? "불러오는 중" : "분석 대기")
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

  let saving = false;

  function bindWatchlistEvents() {
    const picker = window.StockAgent.createSecurityPicker({ root: document.querySelector("#catalog-security-picker"), backend, scope: "catalog" });
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
      if (saving) return;
      const selected = picker.selection();
      if (!selected) {
        showToast("검색 결과에서 등록할 종목을 선택하세요.");
        return;
      }
      const symbol = selected.symbol;
      const existing = state.stocks.find(stock => stock.symbol === symbol && !stock.security_id);
      if (existing && !window.confirm(
        `${existing.symbol} (${existing.name})의 기존 관심종목을 ${selected.name} (${symbol}, ${selected.country})에 연결할까요?\n${selected.note || ""} · 자료 기준 ${selected.source_date || "미상"}\n같은 종목인지 확인하세요. 기존 알림 조건과 과거 브리핑은 유지됩니다.`
      )) return;
      saving = true;
      try {
        if (existing) await backend.linkWatchlist(existing.id, symbol, selected.security_id);
        else await backend.addWatchlist(symbol, selected.security_id);
        state.selectedSymbol = symbol;
        picker.clear();
        showToast(existing ? `${symbol}의 종목정보를 연결했습니다. 기존 조건과 기록을 유지했습니다.` : `${symbol}을 관심종목에 추가했습니다.`);
        await loadWatchlist();
      } catch (error) {
        showToast(`관심종목 등록·연결 실패: ${errorMessage(error)}`);
      } finally { saving = false; }
    });
  }

  return { bindWatchlistEvents, deleteWatchlistItem, loadWatchlist, selectStock };
}

window.StockAgent = { ...window.StockAgent, createWatchlistController };
})();
