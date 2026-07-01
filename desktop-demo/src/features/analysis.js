(() => {
const formatPrice = (value) => new Intl.NumberFormat("ko-KR").format(value);

function verdictClass(verdict) {
  if (verdict === "상승") return "verdict-up";
  if (verdict === "중립") return "verdict-neutral";
  return "verdict-watch";
}

function AnalysisOverview() {
  return `
    <div class="analysis-workspace">
      <section class="status-strip">
        <article class="status-card"><span>선택 종목</span><strong id="selected-symbol"></strong><small id="selected-name"></small></article>
        <article class="status-card"><span>스케줄러</span><strong id="scheduler-status">대기</strong><small>POST /scheduler/run?force=true</small></article>
        <article class="status-card"><span>데이터 기준</span><strong id="data-time"></strong><small>yfinance 시세 스냅샷</small></article>
        <article class="status-card"><span>알림</span><strong id="alert-status"></strong><small id="alert-detail"></small></article>
      </section>
      <section id="latest-analysis-section" class="analysis-card card">
        <div class="analysis-header">
          <div><p id="analysis-time" class="eyebrow"></p><div class="analysis-title-row"><span id="verdict" class="verdict"></span><h2 id="hero-symbol-name"></h2></div></div>
          <div class="price-block"><span>현재가</span><strong id="current-price"></strong><em id="price-change"></em></div>
        </div>
        <p id="analysis-summary" class="analysis-summary"></p>
        <p class="disclaimer">AI 분석은 투자 조언이 아닌 참고 정보입니다. 결과는 FastAPI가 저장한 최신 분석 데이터입니다.</p>
      </section>
      <section class="detail-grid">
        ${InsightPanel("핵심 근거", "AgentAnalysisResult.key_reasons", "reason-list")}
        ${InsightPanel("위험 요인", "AgentAnalysisResult.risk_factors", "risk-list", true)}
      </section>
      ${MetricsPanel()}
    </div>`;
}

function InsightPanel(title, source, id, isRisk = false) {
  return `<article class="card insight-card"><div class="section-heading"><h2>${title}</h2><span>${source}</span></div><ul id="${id}" class="insight-list${isRisk ? " risk-list" : ""}"></ul></article>`;
}

function MetricsPanel() {
  return `<section class="card metrics-card">
    <div class="metric"><span>거래량 비율</span><strong id="volume-ratio"></strong><small>MarketIndicators</small></div>
    <div class="metric"><span>20일 저점</span><strong id="low-price"></strong><small>low_20</small></div>
    <div class="metric"><span>20일 고점</span><strong id="high-price"></strong><small>high_20</small></div>
    <div class="metric"><span>알림 조건</span><strong id="matched-alerts"></strong><small>matched_alert_conditions</small></div>
  </section>`;
}

function AnalysisHistoryPanel() {
  return `<section id="history-section" class="card history-card">
    <div class="section-heading"><div><h2>분석 이력</h2><p>API: GET /stocks/{symbol}/analysis</p></div><button id="latest-button" class="text-button" type="button">최신 분석 보기</button></div>
    <div class="history-table-head" aria-hidden="true"><span>ID</span><span>분석 시각</span><span>판단</span><span>요약</span><span></span></div>
    <div id="history-list" class="history-list"></div>
  </section>`;
}

function renderList(selector, items) {
  document.querySelector(selector).innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function renderAnalysis(stock, analysis) {
  const verdict = document.querySelector("#verdict");
  const hasChange = Number.isFinite(stock.change);
  const sign = hasChange && stock.change >= 0 ? "+" : "";
  document.querySelector("#selected-symbol").textContent = stock.symbol;
  document.querySelector("#selected-name").textContent = stock.name;
  const isLatest = !stock.analyses.length || analysis.id === stock.analyses[0].id;
  document.querySelector("#analysis-time").textContent = `${isLatest ? "LATEST ANALYSIS" : "HISTORY DETAIL"} · ${analysis.time}`;
  verdict.textContent = analysis.verdict;
  verdict.className = `verdict ${verdictClass(analysis.verdict)}`;
  document.querySelector("#hero-symbol-name").textContent = `${stock.name} (${stock.symbol})`;
  document.querySelector("#analysis-summary").textContent = analysis.summary;
  document.querySelector("#current-price").textContent = Number.isFinite(stock.price) ? `${formatPrice(stock.price)}원` : "-";
  const change = document.querySelector("#price-change");
  change.textContent = hasChange ? `${stock.change >= 0 ? "▲" : "▼"} ${sign}${stock.change.toFixed(2)}%` : "-";
  change.className = hasChange ? (stock.change >= 0 ? "positive" : "negative") : "";
  document.querySelector("#volume-ratio").textContent = stock.volumeRatio;
  document.querySelector("#low-price").textContent = `${stock.low20}원`;
  document.querySelector("#high-price").textContent = `${stock.high20}원`;
  document.querySelector("#alert-status").textContent = stock.alertStatus;
  document.querySelector("#alert-detail").textContent = stock.alertDetail;
  document.querySelector("#matched-alerts").textContent = stock.matchedAlerts.length ? `${stock.matchedAlerts.length}개` : "없음";
  document.querySelector("#data-time").textContent = stock.dataTime;
  renderList("#reason-list", analysis.reasons);
  renderList("#risk-list", analysis.risks);
}

function renderHistory(stock, selectedAnalysisId, onSelect) {
  const list = document.querySelector("#history-list");
  if (!stock.analyses.length) {
    list.innerHTML = '<p class="empty-state">저장된 분석 이력이 없습니다.</p>';
    return;
  }
  list.replaceChildren(...stock.analyses.map((analysis) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item${analysis.id === selectedAnalysisId ? " active" : ""}`;
    button.innerHTML = `<span>#${analysis.id}</span><span>${analysis.time}</span><span class="history-verdict">${analysis.verdict}</span><span class="history-summary">${analysis.summary}</span><span class="history-arrow">›</span>`;
    button.addEventListener("click", () => onSelect(analysis.id));
    return button;
  }));
}

window.StockAgent = { ...window.StockAgent, AnalysisOverview, AnalysisHistoryPanel, renderAnalysis, renderHistory };
})();
