(() => {
function AnalysisHistoryPanel() {
  return `<section id="history-section" class="card history-card">
    <div class="section-heading"><div><h2>분석 이력</h2><p>API: GET /stocks/{symbol}/analysis</p></div><button id="latest-button" class="text-button" type="button">최신 분석 보기</button></div>
    <div class="history-table-head" aria-hidden="true"><span>ID</span><span>분석 시각</span><span>판단</span><span>요약</span><span></span></div>
    <div id="history-list" class="history-list"></div>
  </section>`;
}

function renderHistory(stock, selectedAnalysisId, onSelect) {
  const list = document.querySelector("#history-list");
  if (!stock.analyses.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "저장된 분석 이력이 없습니다.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...stock.analyses.map((analysis) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item${analysis.id === selectedAnalysisId ? " active" : ""}`;
    const id = document.createElement("span");
    id.textContent = `#${analysis.id}`;
    const time = document.createElement("span");
    time.textContent = analysis.time;
    const verdict = document.createElement("span");
    verdict.className = "history-verdict";
    verdict.textContent = analysis.verdict;
    const summary = document.createElement("span");
    summary.className = "history-summary";
    summary.textContent = analysis.summary;
    const arrow = document.createElement("span");
    arrow.className = "history-arrow";
    arrow.textContent = "›";
    button.append(id, time, verdict, summary, arrow);
    button.addEventListener("click", () => onSelect(analysis.id));
    return button;
  }));
}

window.StockAgent = { ...window.StockAgent, AnalysisHistoryPanel, renderHistory };
})();
