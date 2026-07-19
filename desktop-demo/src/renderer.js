const {
  AppShell,
  WatchlistPanel,
  AnalysisOverview,
  AnalysisHistoryPanel,
  AlertConditionsPanel,
  renderWatchlist,
  renderAnalysis,
  renderHistory,
  renderAlertConditions,
  showToast,
  showDialog,
  bindDialogEvents,
  state,
  emptyAnalysis,
  errorMessage,
  selectedStockView,
  createBackendService,
  createAnalysisController,
  createWatchlistController,
  createAlertsController,
  bindNavigationEvents,
  showView
} = window.StockAgent;

const backend = createBackendService();
const noop = () => {};
const controllerRefs = {
  selectStock: noop,
  deleteWatchlistItem: noop,
  selectAnalysis: noop,
  deleteAlertCondition: noop
};

function renderScreen() {
  const stock = selectedStockView();
  renderWatchlist(state.stocks, state.selectedSymbol, controllerRefs.selectStock, controllerRefs.deleteWatchlistItem);
  renderAnalysis(stock, state.selectedAnalysis || emptyAnalysis(stock.symbol));
  renderHistory(stock, state.selectedAnalysis?.id, controllerRefs.selectAnalysis);
  renderAlertConditions(state.alertConditions, controllerRefs.deleteAlertCondition);
}

document.querySelector("#app").innerHTML = AppShell(`
  <div class="view-stack">
    <section id="watchlist-view" class="app-view">${WatchlistPanel()}</section>
    <section id="analysis-view" class="app-view" hidden>${AnalysisOverview()}</section>
    <section id="history-view" class="app-view" hidden><div class="analysis-workspace">${AnalysisHistoryPanel()}</div></section>
    <section id="alerts-view" class="app-view" hidden><div class="analysis-workspace">${AlertConditionsPanel()}</div></section>
  </div>
`);

async function initialize() {
  if (!backend) {
    document.querySelector("#backend-connection").textContent = "BACKEND 사용 불가";
    document.querySelector("#backend-detail").textContent = "Electron preload API를 찾지 못했습니다.";
    renderScreen();
    return;
  }

  const analysisController = createAnalysisController({ backend, renderScreen, showToast, showDialog, showView });
  const watchlistController = createWatchlistController({
    backend,
    renderScreen,
    showToast,
    showView,
    loadSelectedAnalysis: analysisController.loadSelectedAnalysis
  });
  const alertsController = createAlertsController({
    backend,
    showToast,
    showDialog,
    renderAlertConditions
  });

  controllerRefs.selectStock = watchlistController.selectStock;
  controllerRefs.deleteWatchlistItem = watchlistController.deleteWatchlistItem;
  controllerRefs.selectAnalysis = analysisController.selectAnalysis;
  controllerRefs.deleteAlertCondition = alertsController.deleteAlertCondition;

  bindNavigationEvents();
  bindDialogEvents();
  watchlistController.bindWatchlistEvents();
  analysisController.bindAnalysisEvents();
  alertsController.bindAlertsEvents();

  try {
    const connection = await backend.status();
    document.querySelector("#backend-connection").textContent = "BACKEND 연결됨";
    document.querySelector("#backend-detail").textContent = connection.baseUrl;
    await Promise.all([watchlistController.loadWatchlist(), alertsController.loadAlertConditions()]);
    document.querySelector("#alert-symbol-input").value = state.selectedSymbol || "";
  } catch (error) {
    document.querySelector("#backend-connection").textContent = "BACKEND 연결 실패";
    document.querySelector("#backend-detail").textContent = errorMessage(error);
    renderScreen();
    showToast(`백엔드 연결 실패: ${errorMessage(error)}`);
  }
}

renderScreen();
initialize();
