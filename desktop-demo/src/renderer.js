const {
  AppRoot, AppShell, LoginPage, WatchlistPanel, AnalysisOverview, AnalysisHistoryPanel,
  AlertConditionsPanel, renderWatchlist, renderAnalysis, renderHistory, renderAlertConditions,
  showToast, showDialog, bindDialogEvents, state, emptyAnalysis, errorMessage,
  selectedStockView, createBackendService, createAnalysisController, createWatchlistController,
  createAlertsController, createAuthController, bindNavigationEvents, showView
} = window.StockAgent;

const backend = createBackendService();
const auth = window.desktop?.auth || null;
const noop = () => {};
const controllerRefs = { selectStock: noop, deleteWatchlistItem: noop, selectAnalysis: noop, deleteAlertCondition: noop };

document.querySelector("#app").innerHTML = AppRoot();
const authView = document.querySelector("#auth-view");
const applicationView = document.querySelector("#application-view");

function buildApplicationShell() {
  applicationView.innerHTML = AppShell(`
    <div class="view-stack">
      <section id="watchlist-view" class="app-view">${WatchlistPanel()}</section>
      <section id="analysis-view" class="app-view" hidden>${AnalysisOverview()}</section>
      <section id="history-view" class="app-view" hidden><div class="analysis-workspace">${AnalysisHistoryPanel()}</div></section>
      <section id="alerts-view" class="app-view" hidden><div class="analysis-workspace">${AlertConditionsPanel()}</div></section>
    </div>
  `);
}

function resetApplication() {
  state.stocks = [];
  state.selectedSymbol = null;
  state.selectedAnalysis = null;
  state.analysisHistory = [];
  state.analysisDetails = new Map();
  state.alertConditions = [];
  buildApplicationShell();
}

buildApplicationShell();

function renderScreen() {
  const stock = selectedStockView();
  renderWatchlist(state.stocks, state.selectedSymbol, controllerRefs.selectStock, controllerRefs.deleteWatchlistItem);
  renderAnalysis(stock, state.selectedAnalysis || emptyAnalysis(stock.symbol));
  renderHistory(stock, state.selectedAnalysis?.id, controllerRefs.selectAnalysis);
  renderAlertConditions(state.alertConditions, controllerRefs.deleteAlertCondition);
}

function updateAccountMenu(account) {
  document.querySelector("#account-provider").textContent = `${account.login_provider.toUpperCase()} 계정`;
  document.querySelector("#account-id").textContent = account.id;
}

async function initializeApplication(account) {
  const analysisController = createAnalysisController({ backend, renderScreen, showToast, showDialog, showView });
  const watchlistController = createWatchlistController({
    backend, renderScreen, showToast, showView,
    loadSelectedAnalysis: analysisController.loadSelectedAnalysis
  });
  const alertsController = createAlertsController({ backend, showToast, showDialog, renderAlertConditions });

  controllerRefs.selectStock = watchlistController.selectStock;
  controllerRefs.deleteWatchlistItem = watchlistController.deleteWatchlistItem;
  controllerRefs.selectAnalysis = analysisController.selectAnalysis;
  controllerRefs.deleteAlertCondition = alertsController.deleteAlertCondition;

  bindNavigationEvents();
  bindDialogEvents();
  watchlistController.bindWatchlistEvents();
  analysisController.bindAnalysisEvents();
  alertsController.bindAlertsEvents();
  document.querySelector("#logout-button").addEventListener("click", () => authController.logout().catch((error) => showToast(errorMessage(error))));
  updateAccountMenu(account);

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

let authController = null;
function renderAuthState(view) {
  const authenticated = view.status === "authenticated";
  authView.hidden = authenticated;
  applicationView.hidden = !authenticated;
  if (authenticated) {
    updateAccountMenu(view.account);
    return;
  }
  authView.innerHTML = LoginPage(view);
  authView.querySelector("[data-auth-login]")?.addEventListener("click", () => authController.login().catch(() => {}));
}

renderScreen();
if (!auth || !backend) {
  renderAuthState({ status: "anonymous", error: "Electron preload 인증 API를 찾지 못했습니다." });
} else {
  authController = createAuthController({ auth, render: renderAuthState, initializeApplication, resetApplication });
  authController.start().catch((error) => renderAuthState({ status: "anonymous", error: errorMessage(error) }));
}
