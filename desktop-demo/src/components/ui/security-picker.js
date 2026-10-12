(() => {
function createSecurityPicker({ root, backend, scope, onSelect = () => {} }) {
  root.innerHTML = `<div class="security-picker">
    <label>종목명 또는 코드 <input data-security-query type="search" placeholder="예: 삼성전자, AAPL" maxlength="100"></label>
    <div class="security-picker-options"><label>시장 <select data-security-country><option value="">한국·미국</option><option value="KR">한국</option><option value="US">미국</option></select></label>
    <label>정렬 <select data-security-sort><option value="relevance">관련도순</option><option value="name_asc">종목명 오름차순</option><option value="name_desc">종목명 내림차순</option><option value="code_asc">코드 오름차순</option></select></label>
    <button type="button" data-security-refresh>목록 새로고침</button></div>
    <p data-security-status role="status" aria-live="polite"></p><div data-security-results class="security-results"></div>
    <button type="button" data-security-more hidden>검색 결과 더 보기</button>
    <p data-security-selection>선택한 종목 없음</p><button type="button" data-security-clear>선택 해제</button></div>`;
  const el = (s) => root.querySelector(`[data-security-${s}]`);
  let selected = null, cursor = null, version = 0, timer = null, loading = false;
  function choose(row) {
    selected = row;
    el("selection").textContent = row ? `선택: ${row.name} (${row.symbol}) · ${row.note}` : "선택한 종목 없음";
    el("results").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === row?.key)));
    onSelect(row);
  }
  async function load(append = false) {
    if (append && (loading || !cursor)) return;
    const requestVersion = ++version;
    loading = true;
    el("status").textContent = "종목 목록을 조회하고 있습니다…";
    if (!append) { cursor = null; el("results").replaceChildren(); }
    el("more").hidden = true;
    try {
      const result = await backend.searchSecurities({ scope, q: el("query").value,
        sort: el("sort").value, country: el("country").value, cursor: append ? cursor : null });
      if (requestVersion !== version || !root.isConnected) return;
      const states = { active: "상장", delisted: "상장폐지", unknown: "상태 미확인", pending: "상장 예정", historical: "과거 기록" };
      for (const row of result.items) {
        const button = document.createElement("button"); button.type = "button";
        button.dataset.key = row.key; button.disabled = !row.selectable;
        button.setAttribute("aria-pressed", String(selected?.key === row.key));
        button.textContent = `${row.name} · ${row.symbol} · ${row.country} · ${states[row.status] || row.status}\n${row.note}${row.source_date ? ` · 자료 기준 ${row.source_date}` : ""}${row.selectable ? "" : " · 현재 선택 불가"}`;
        button.addEventListener("click", () => choose(row)); el("results").append(button);
      }
      cursor = result.next_cursor; el("more").hidden = !cursor;
      const warning = scope === "briefings" ? "관심종목에서 삭제했거나 상폐된 종목의 기록도 포함합니다."
        : result.catalog.filter((c) => c.state !== "READY").map((c) => `${c.country} ${c.state === "UNAVAILABLE" ? "종목 목록 준비 전" : "목록 갱신 지연"}`).join(" · ");
      el("status").textContent = `${result.total}개 결과${warning ? " · " + warning : ""}`;
    } catch (error) {
      if (requestVersion === version) el("status").textContent = `검색 실패: ${error.message || error}`;
    } finally { if (requestVersion === version) loading = false; }
  }
  el("query").addEventListener("input", () => {
    ++version; choose(null); el("results").replaceChildren(); el("more").hidden = true;
    clearTimeout(timer); timer = setTimeout(() => load(), 250);
  });
  el("query").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); clearTimeout(timer); load(); }
  });
  el("sort").addEventListener("change", () => load());
  el("country").addEventListener("change", () => { choose(null); load(); });
  el("more").addEventListener("click", () => load(true));
  el("refresh").addEventListener("click", () => { choose(null); load(); });
  el("clear").addEventListener("click", () => choose(null));
  load();
  return { selection: () => selected, clear: () => choose(null), refresh: () => load() };
}
window.StockAgent = { ...window.StockAgent, createSecurityPicker };
})();
