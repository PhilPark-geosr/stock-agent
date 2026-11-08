(() => {
const state = {
  stocks: [],
  selectedSymbol: null,
  selectedAnalysis: null,
  analysisHistory: [],
  analysisHistoryError: null,
  analysisDetails: new Map(),
  alertConditions: []
};

function formatDate(value) {
  if (!value || !/(Z|[+-]\d{2}:\d{2})$/i.test(value)) return "기록 시각 미확인";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "기록 시각 미확인";
  return date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false }) + " KST";
}

function basisLabel(basis) {
  return basis?.interval === "1d" && basis.session_date
    ? `${basis.session_date} 일봉 기준 · 시장 현지일`
    : "가격 기준 거래일 미확인";
}

function phaseLabel(basis) {
  switch (basis?.collection_phase) {
    case "during_session": return "장중 기준";
    case "after_session": return "정규장 종료 후 수집";
    case "boundary": return "장 마감 경계에서 수집";
    default: return "수집 시점 상태 미확인";
  }
}

function phaseExplanation(basis) {
  if (basis?.collection_phase === "after_session") return "공급자의 마감 가격 반영은 확인되지 않았습니다.";
  if (basis?.collection_phase === "during_session") return "당시 정규장 중 수집한 값으로, 마감 가격이 아닙니다.";
  if (basis?.collection_phase === "boundary") return "요청 도중 정규장이 종료되어 장중·장후 값을 구분할 수 없습니다.";
  const reasons = {
    calendar_out_of_range: "이 거래일은 지원하는 거래소 일정 범위 밖입니다.",
    calendar_unavailable: "거래소 일정을 확인하지 못했습니다.",
    not_a_trading_session: "일봉의 날짜가 거래소 휴장일과 일치해 확인이 필요합니다.",
    before_session_open: "해당 일봉의 정규장 시작 전 수집되어 확인이 필요합니다.",
    market_timezone_mismatch: "거래소와 데이터의 시간대가 일치하지 않습니다.",
    unsupported_or_missing_market: "거래소 정보가 없거나 지원하지 않는 시장·상품입니다.",
    invalid_collection_window: "수집 시각의 순서가 맞지 않아 상태를 판단하지 않았습니다."
  };
  return reasons[basis?.phase_reason] || "거래일 또는 당시 수집 시각의 근거가 없습니다.";
}

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
    dataTimestamp: null,
    chartBasis: null
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
    dataTimestamp: result.data_timestamp,
    chartBasis: result.chart_basis || null
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
    dataTimestamp: result.data_timestamp,
    chartBasis: result.chart_basis || null
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
    dataTime: basisLabel(analysis.chartBasis),
    priceLabel: analysis.chartBasis?.interval === "1d" ? "일봉 기준 가격" : "분석 기준 가격",
    phaseLabel: phaseLabel(analysis.chartBasis),
    finalityLabel: phaseExplanation(analysis.chartBasis),
    collectedTime: analysis.chartBasis?.collected_at ? `가격 수집 완료 ${formatDate(analysis.chartBasis.collected_at)}` : "",
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
  basisLabel,
  phaseLabel,
  phaseExplanation,
  selectedStockView
};
})();
