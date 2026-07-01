const {
  AppShell,
  showToast,
  WatchlistPanel,
  renderWatchlist,
  AnalysisOverview,
  AnalysisHistoryPanel,
  renderAnalysis,
  renderHistory,
  AlertConditionsPanel,
  renderAlertConditions
} = window.StockAgent;

const backend = window.desktop?.backend;
const state = {
  stocks: [],
  selectedSymbol: null,
  selectedAnalysis: null,
  analysisHistory: [],
  analysisDetails: new Map(),
  alertConditions: []
};

const formatDate = (value) => value
  ? new Date(value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false })
  : "-";

const asNumber = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
};

const optionalNumber = (value) => value == null ? null : asNumber(value);

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function emptyAnalysis(symbol = "-") {
  return {
    id: null,
    symbol,
    time: "분석 결과 없음",
    verdict: "대기",
    summary: "저장된 분석이 없습니다. 수동 분석 실행을 눌러 분석을 생성하세요.",
    reasons: ["백엔드 분석 결과를 기다리고 있습니다."],
    risks: ["Gemini API 키와 네트워크 연결이 필요할 수 있습니다."],
    supportLevels: {},
    shouldAlert: false,
    triggeredAlerts: [],
    alertReason: "알림 조건 미확인",
    dataTimestamp: null
  };
}

function normalizeAnalysis(result) {
  return {
    id: result.id,
    symbol: result.symbol,
    time: formatDate(result.analyzed_at),
    verdict: result.overall_judgment,
    summary: result.summary,
    reasons: result.key_reasons || [],
    risks: result.risk_factors || [],
    supportLevels: result.support_levels || {},
    shouldAlert: Boolean(result.should_alert),
    triggeredAlerts: result.triggered_alerts || [],
    alertReason: result.alert_reason || "알림 조건 미충족",
    dataTimestamp: result.data_timestamp
  };
}

function normalizeHistoryItem(result) {
  return {
    id: result.id,
    symbol: result.symbol,
    time: formatDate(result.analyzed_at),
    verdict: result.overall_judgment,
    summary: result.summary,
    reasons: [],
    risks: [],
    supportLevels: {},
    shouldAlert: Boolean(result.should_alert),
    triggeredAlerts: result.triggered_alerts || [],
    alertReason: result.should_alert ? "알림 조건 충족" : "알림 조건 미충족",
    dataTimestamp: result.data_timestamp
  };
}

function selectedStockView() {
  const selected = state.stocks.find((stock) => stock.symbol === state.selectedSymbol);
  const analysis = state.selectedAnalysis || emptyAnalysis(state.selectedSymbol || "-");
  const indicators = analysis.supportLevels || {};
  return {
    symbol: selected?.symbol || analysis.symbol || "-",
    name: selected?.name || selected?.symbol || analysis.symbol || "선택된 종목 없음",
    price: optionalNumber(indicators.latest_close),
    change: optionalNumber(indicators.change_percent),
    volumeRatio: indicators.volume_ratio_20 == null ? "-" : `${asNumber(indicators.volume_ratio_20).toFixed(2)}x`,
    low20: indicators.low_20 == null ? "-" : new Intl.NumberFormat("ko-KR").format(asNumber(indicators.low_20)),
    high20: indicators.high_20 == null ? "-" : new Intl.NumberFormat("ko-KR").format(asNumber(indicators.high_20)),
    alertStatus: analysis.shouldAlert ? "전송 대상" : "조건 미충족",
    alertDetail: analysis.alertReason,
    matchedAlerts: analysis.triggeredAlerts,
    dataTime: formatDate(analysis.dataTimestamp),
    analyses: state.analysisHistory
  };
}

function renderScreen() {
  const stock = selectedStockView();
  renderWatchlist(state.stocks, state.selectedSymbol, selectStock, deleteWatchlistItem);
  renderAnalysis(stock, state.selectedAnalysis || emptyAnalysis(stock.symbol));
  renderHistory(stock, state.selectedAnalysis?.id, selectAnalysis);
  renderAlertConditions(state.alertConditions, deleteAlertCondition);
}

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

async function loadSelectedAnalysis() {
  const symbol = state.selectedSymbol;
  if (!symbol) return;
  document.querySelector("#scheduler-status").textContent = "데이터 조회 중";
  try {
    const [latestResult, historyResult] = await Promise.all([
      backend.latestAnalysis(symbol),
      backend.analysisHistory(symbol)
    ]);
    if (state.selectedSymbol !== symbol) return;
    const latest = normalizeAnalysis(latestResult);
    state.analysisDetails.set(latest.id, latest);
    state.selectedAnalysis = latest;
    state.analysisHistory = historyResult.map(normalizeHistoryItem);
    if (!state.analysisHistory.some((item) => item.id === latest.id)) {
      state.analysisHistory.unshift(latest);
    }
    document.querySelector("#scheduler-status").textContent = "대기";
    const stock = state.stocks.find((item) => item.symbol === symbol);
    if (stock) stock.alertStatus = latest.shouldAlert ? "전송 대상" : "조건 미충족";
    renderScreen();
  } catch (error) {
    if (state.selectedSymbol !== symbol) return;
    state.selectedAnalysis = emptyAnalysis(symbol);
    state.analysisHistory = [];
    document.querySelector("#scheduler-status").textContent = "조회 실패";
    renderScreen();
    showToast(`분석 조회 실패: ${errorMessage(error)}`);
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

async function selectAnalysis(analysisId) {
  const cached = state.analysisDetails.get(analysisId);
  if (cached) {
    state.selectedAnalysis = cached;
    renderScreen();
    showView("analysis-view");
    return;
  }
  try {
    const result = await backend.analysisById(state.selectedSymbol, analysisId);
    const analysis = normalizeAnalysis(result);
    state.analysisDetails.set(analysisId, analysis);
    state.selectedAnalysis = analysis;
    renderScreen();
    showView("analysis-view");
  } catch (error) {
    showToast(`이력 상세 조회 실패: ${errorMessage(error)}`);
  }
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

async function loadAlertConditions() {
  state.alertConditions = await backend.listAlertConditions();
  renderAlertConditions(state.alertConditions, deleteAlertCondition);
}

async function deleteAlertCondition(conditionId) {
  try {
    await backend.deleteAlertCondition(conditionId);
    showToast(`알림 조건 #${conditionId}을 삭제했습니다.`);
    await loadAlertConditions();
  } catch (error) {
    showToast(`알림 조건 삭제 실패: ${errorMessage(error)}`);
  }
}

document.querySelector("#app").innerHTML = AppShell(`
  <div class="view-stack">
    <section id="watchlist-view" class="app-view">${WatchlistPanel()}</section>
    <section id="analysis-view" class="app-view" hidden>${AnalysisOverview()}</section>
    <section id="history-view" class="app-view" hidden><div class="analysis-workspace">${AnalysisHistoryPanel()}</div></section>
    <section id="alerts-view" class="app-view" hidden><div class="analysis-workspace">${AlertConditionsPanel()}</div></section>
  </div>
`);

function showView(viewId) {
  document.querySelectorAll(".app-view").forEach((view) => {
    view.hidden = view.id !== viewId;
  });
  document.querySelectorAll(".flow-step").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

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

document.querySelector("#latest-button").addEventListener("click", async () => {
  await loadSelectedAnalysis();
  showView("analysis-view");
});

document.querySelector("#run-analysis-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  document.querySelector("#scheduler-status").textContent = "실행 중";
  try {
    const result = await backend.runScheduler();
    const analyzed = result.symbols_analyzed?.length || 0;
    const failed = result.symbols_failed?.length || 0;
    showToast(`스케줄러 완료: 성공 ${analyzed}개, 실패 ${failed}개`);
    await loadSelectedAnalysis();
  } catch (error) {
    document.querySelector("#scheduler-status").textContent = "실패";
    showToast(`스케줄러 실행 실패: ${errorMessage(error)}`);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#alert-condition-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const symbolInput = document.querySelector("#alert-symbol-input");
  const ruleInput = document.querySelector("#alert-rule-input");
  const status = document.querySelector("#alert-condition-status");
  const symbol = (symbolInput.value.trim() || state.selectedSymbol || "").toUpperCase();
  const rule = ruleInput.value.trim();
  if (!symbol || !rule) {
    status.textContent = "종목 코드와 알림 조건을 입력하세요.";
    return;
  }
  status.textContent = "Gemini로 조건을 검증하고 있습니다...";
  try {
    const condition = await backend.addAlertCondition(symbol, rule);
    ruleInput.value = "";
    status.textContent = condition.validation_summary;
    await loadAlertConditions();
    showToast(`알림 조건 #${condition.id}을 저장했습니다.`);
  } catch (error) {
    status.textContent = `저장 실패: ${errorMessage(error)}`;
  }
});

document.querySelector("#kakao-login-button").addEventListener("click", async () => {
  try {
    await backend.openKakaoLogin();
    showToast("브라우저에서 카카오 로그인을 완료하세요.");
  } catch (error) {
    showToast(`카카오 로그인 열기 실패: ${errorMessage(error)}`);
  }
});

document.querySelectorAll(".flow-step").forEach((button) => {
  button.addEventListener("click", () => {
    showView(button.dataset.view);
  });
});

async function initialize() {
  if (!backend) {
    document.querySelector("#backend-connection").textContent = "BACKEND 사용 불가";
    document.querySelector("#backend-detail").textContent = "Electron preload API를 찾지 못했습니다.";
    renderScreen();
    return;
  }
  try {
    const connection = await backend.status();
    document.querySelector("#backend-connection").textContent = "BACKEND 연결됨";
    document.querySelector("#backend-detail").textContent = connection.baseUrl;
    await Promise.all([loadWatchlist(), loadAlertConditions()]);
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
