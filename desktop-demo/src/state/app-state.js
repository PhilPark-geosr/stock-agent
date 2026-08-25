(() => {
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
    alertStatus: "평가 중단",
    alertDetail: "사용자별 알림 평가·발송은 다음 설계 단계에서 활성화됩니다.",
    matchedAlerts: [],
    dataTime: formatDate(analysis.dataTimestamp),
    analyses: state.analysisHistory
  };
}

window.StockAgent = {
  ...window.StockAgent,
  state,
  emptyAnalysis,
  errorMessage,
  normalizeAnalysis,
  normalizeHistoryItem,
  selectedStockView
};
})();
