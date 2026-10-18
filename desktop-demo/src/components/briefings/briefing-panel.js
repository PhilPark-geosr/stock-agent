(function (scope) {
const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const labels = { preparing: "준비 중", completed: "완료", partial: "부분 완료", deferred: "판단 보류", failed: "실패",
  pending: "전달 대기", sending: "전송 중", sent: "발송 접수 성공", unknown: "전송 결과 확인 불가",
  not_requested: "수신 꺼짐", not_connected: "카카오 미연결", cancelled: "전달 취소" };
function BriefingPanel() {
  return `<div class="briefing-panel">
    <header class="briefing-heading"><div><p class="eyebrow">나의 투자 브리핑</p><h2>오늘은 어떤 종목을 살펴볼까요?</h2>
      <p>선택한 종목의 차트와 뉴스·공시를 모아, 이전 판단과 달라진 점을 정리해 드립니다.</p></div>
      <button type="button" class="secondary-button" data-refresh-briefing>목록 새로고침</button></header>
    <form data-briefing-form>
      <div class="briefing-builder">
        <section class="briefing-card"><div class="briefing-section-heading"><h3><span class="briefing-step">1</span> 살펴볼 관심종목</h3>
          <label class="briefing-market">시장 <select name="market"><option value="KR">한국</option><option value="US">미국</option></select></label></div>
          <p class="briefing-muted">이번 브리핑에 담을 종목을 골라주세요. 최대 30개까지 선택할 수 있습니다.</p>
          <div class="briefing-selection-tools"><input type="search" data-target-search placeholder="종목 코드로 찾기" aria-label="브리핑 관심종목 검색">
            <button type="button" data-select-all>전체 선택</button><button type="button" data-clear-selection>선택 해제</button></div>
          <div class="briefing-targets" data-briefing-targets aria-label="분석 대상 관심종목"><p>관심종목을 불러오는 중입니다.</p></div>
          <div class="briefing-selection-footer"><strong data-selected-count aria-live="polite">0개 선택</strong>
            <button type="button" class="briefing-text-button" data-manage-watchlist>관심종목 관리 →</button></div>
        </section>
        <section class="briefing-card"><h3><span class="briefing-step">2</span> 분석 조건</h3>
          <label class="briefing-field">어떤 브리핑을 만들까요?<select name="purpose"><option value="pre_market">장전 · 오늘의 판단 준비</option><option value="post_market">장후 · 오늘의 흐름 복기</option></select></label>
          <p data-purpose-hint class="briefing-hint"></p>
          <label class="briefing-field">차트를 얼마나 살펴볼까요?<span class="briefing-period"><input name="n" type="number" min="1" max="250" placeholder="기간 입력" required><span>거래일</span></span></label>
          <div class="briefing-presets"><button type="button" data-days="20">20거래일</button><button type="button" data-days="60">60거래일</button><button type="button" data-days="120">120거래일</button></div>
          <p class="briefing-muted">주말과 휴장일을 제외한 1~250거래일입니다. 기간을 직접 입력하거나 선택하세요.</p>
          <div data-source-notice class="briefing-hint"></div>
        </section>
      </div>
      <div class="briefing-review"><div><strong data-briefing-summary>관심종목과 분석 기간을 선택해 주세요.</strong>
        <p data-delivery-summary>결과는 이 화면에 보관됩니다.</p><p data-generation-help class="briefing-hint"></p></div>
        <button class="primary-button" type="submit" data-generate-briefing disabled>선택한 종목으로 브리핑 만들기</button></div>
      <details class="briefing-card briefing-automation"><summary>자동 제공 · 카카오 수신 설정</summary>
        <p data-saved-schedule class="briefing-muted"></p>
        <p>저장하면 현재 선택한 종목과 관찰기간을 자동 제공에 사용합니다. 이번 생성에서 바꾼 선택은 저장 전까지 자동 제공에 영향을 주지 않습니다.</p>
        <div class="briefing-options"><label><input type="checkbox" name="pre_market_enabled"> 장전 자동 제공</label>
          <label><input type="checkbox" name="post_market_enabled"> 장후 자동 제공</label>
          <label><input type="checkbox" name="kakao_enabled"> 완성된 브리핑을 카카오로 받기</label></div>
        <p data-kakao-hint class="briefing-muted"></p>
        <p class="briefing-muted">현재 자동 제공 시간: 개장 30분 전 · 마감 15분 후. 백엔드가 켜져 있어야 합니다.</p>
        <button type="button" class="secondary-button" data-save-briefing>현재 종목·기간으로 제공 설정 저장</button>
      </details>
    </form>
    <p data-briefing-status role="status" aria-live="polite" class="briefing-feedback"></p>
    <section class="briefing-history-section"><h3>지난 브리핑 이어보기</h3><p class="briefing-muted">생성 당시 선택한 종목과 근거를 다시 확인할 수 있습니다.</p>
      <div class="briefing-layout"><div><div data-briefing-history></div><button type="button" data-more-briefings hidden>이전 브리핑 더 보기</button></div>
      <article data-briefing-detail class="briefing-card"><div class="briefing-empty"><h3>판단의 흐름을 한곳에서</h3><p>브리핑을 만들거나 왼쪽 이력을 선택하면<br>종목별 결론과 이전 판단의 변화를 확인할 수 있습니다.</p></div></article></div></section>
  </div>`;
}

function renderBriefingTargets(symbols, selected, search = "") {
  if (!symbols.length) return '<div class="briefing-empty"><h4>이 시장의 관심종목이 아직 없어요.</h4><p>관심종목을 먼저 등록한 뒤 이곳에서 분석 대상을 골라주세요.</p></div>';
  const matches = symbols.filter((s) => s.toLowerCase().includes(search.trim().toLowerCase()));
  if (!matches.length) return '<p class="briefing-empty">검색어와 일치하는 관심종목이 없습니다.</p>';
  return matches.map((symbol) => `<label class="briefing-target ${selected.has(symbol) ? "is-selected" : ""}"><input type="checkbox" data-target-symbol="${escape(symbol)}" ${selected.has(symbol) ? "checked" : ""}>
    <span><strong>${escape(symbol)}</strong><small>${symbol.endsWith(".KS") ? "코스피" : symbol.endsWith(".KQ") ? "코스닥" : "미국"}</small></span></label>`).join("");
}
function renderBriefing(run) {
  const result = run.result;
  const sources = run.snapshot?.evidence || [];
  const sourceLink = (source) => /^https?:\/\//i.test(source.url || "")
    ? `<a href="${escape(source.url)}" target="_blank" rel="noopener noreferrer">${escape(source.source)}</a>` : escape(source.source);
  return `<h3>${escape(run.trade_date)} ${run.purpose === "pre_market" ? "장전" : "장후"} · ${escape(labels[run.status] || run.status)}</h3>
    <p>관찰기간 ${escape(run.context.n)}거래일 · 기준 ${escape(run.context.cutoff_at)}</p>
    <p class="briefing-muted">분석 대상: ${(run.context.symbols || []).map(escape).join(" · ")}</p>
    <p>카카오: ${escape(labels[run.delivery?.status] || "전달 대상 없음")} ${escape(run.delivery?.reason || "")}</p>
    ${run.failure_reason ? `<p role="alert">${escape(run.failure_reason)}</p>` : ""}
    ${result ? `<p>${escape(result.summary)}</p>${result.items.map((item) => `<section class="briefing-item">
      <h4>${escape(item.symbol)} · ${escape(item.verdict)}</h4><p>${escape(item.reason)}</p>
      <p><strong>${escape(item.comparison)}</strong> ${escape(item.comparison_reason)}</p>
      <ul>${item.evidence_ids.map((id) => { const s = sources.find((e) => e.id === id); return s ? `<li>${sourceLink(s)} · ${escape(s.published_at)}<p>${escape(s.text)}</p></li>` : ""; }).join("")}</ul>
      <p>${item.limitations.map(escape).join(" · ")}</p><p>다음 관찰: ${escape(item.next_observation)}</p></section>`).join("")}` : ""}
    ${run.snapshot ? `<details><summary>자료 수집 범위와 한계</summary><ul>${run.snapshot.sources.map((s) => `<li>${escape(s.symbol)} · ${escape(s.source)}: ${escape(({ok: "조회 완료", empty: "조회 결과 없음", partial: "일부 자료", failed: "조회 실패", unconfigured: "연결 설정 필요", delayed: "자료 지연"})[s.status] || s.status)} — ${escape(s.detail)}</li>`).join("")}</ul>
      <p>기준 시각·대상·수집 한도에 따라 제외한 자료: ${run.snapshot.excluded.length}건</p>
      ${sources.filter((s) => s.kind === "chart").map((s) => `<h4>${escape(s.symbol)} 일봉</h4><table><thead><tr><th>거래일</th><th>시가</th><th>고가</th><th>저가</th><th>종가</th><th>거래량</th></tr></thead><tbody>${(s.data.candles || []).map((c) => `<tr>${[c.date,c.open,c.high,c.low,c.close,c.volume].map((v) => `<td>${escape(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`).join("")}</details>` : ""}
    ${run.prompt_content ? `<details><summary>이 브리핑에 사용한 분석 지침</summary><pre>${escape(run.prompt_content)}</pre></details>` : ""}
    ${["failed", "unknown", "not_connected", "not_requested", "cancelled"].includes(run.delivery?.status) ? `<button type="button" data-redeliver>기존 브리핑 다시 전달</button>` : ""}
    <button type="button" class="secondary-button" data-reanalyze>이 종목으로 새 브리핑 준비</button>`;
}
const api = { BriefingPanel, renderBriefing, renderBriefingTargets };
if (typeof module !== "undefined") module.exports = api;
if (scope) scope.StockAgent = { ...scope.StockAgent, ...api };
})(typeof window !== "undefined" ? window : null);
