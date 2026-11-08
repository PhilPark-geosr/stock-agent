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
        <article class="status-card"><span>수동 분석</span><strong id="scheduler-status">대기</strong><small>POST /stocks/{symbol}/analysis</small></article>
        <article class="status-card"><span>가격 기준</span><strong id="data-time"></strong><small id="basis-finality"></small><small id="basis-collected"></small></article>
        <article class="status-card"><span>알림</span><strong id="alert-status"></strong><small id="alert-detail"></small></article>
      </section>
      <section id="latest-analysis-section" class="analysis-card card">
        <div class="analysis-header">
          <div><p id="analysis-time" class="eyebrow"></p><div class="analysis-title-row"><span id="verdict" class="verdict"></span><h2 id="hero-symbol-name"></h2></div></div>
          <div class="price-block"><span id="basis-price-label">분석 기준 가격</span><strong id="current-price"></strong><small id="price-basis"></small><em id="price-change"></em></div>
        </div>
        <p id="analysis-summary" class="analysis-summary"></p>
        <p class="disclaimer">분석에 사용된 당시 가격과 판단입니다. 가격 기준과 분석 기록 시각을 함께 확인하세요.</p>
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
  document.querySelector("#analysis-time").textContent = `${isLatest ? "최근 기록한 분석" : "과거 분석"} · 분석 기록 ${analysis.time}`;
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
  document.querySelector("#basis-price-label").textContent = stock.priceLabel;
  document.querySelector("#price-basis").textContent = `${stock.dataTime} · ${stock.phaseLabel}`;
  document.querySelector("#basis-finality").textContent = stock.finalityLabel;
  document.querySelector("#basis-collected").textContent = stock.collectedTime;
  renderList("#reason-list", analysis.reasons);
  renderList("#risk-list", analysis.risks);
}

window.StockAgent = { ...window.StockAgent, AnalysisOverview, renderAnalysis };
})();
