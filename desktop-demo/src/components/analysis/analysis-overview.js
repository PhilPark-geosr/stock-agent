(() => {
const { InsightPanel, MetricsPanel } = window.StockAgent;
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

function renderList(selector, items) {
  const list = document.querySelector(selector);
  list.replaceChildren(...items.map((item) => {
    const row = document.createElement("li");
    row.textContent = item;
    return row;
  }));
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

window.StockAgent = { ...window.StockAgent, AnalysisOverview, renderAnalysis };
})();
