(() => {
function createBriefingController({ backend }) {
  const root = document.querySelector("#briefing-view");
  const el = (selector) => root.querySelector(selector);
  const form = el("form"), status = el("[data-briefing-status]"), history = el("[data-briefing-history]");
  const detail = el("[data-briefing-detail]"), more = el("[data-more-briefings]");
  const targets = el("[data-briefing-targets]"), search = el("[data-target-search]"), submit = el("[data-generate-briefing]");
  let offset = 0, loadingHistory = false, busy = false, loading = false;
  let generationRequest = null, currentRun = null, originalId = null;
  let options = null, saved = null, loadedMarket = null, loadVersion = 0, detailVersion = 0;
  let selected = new Set();
  const retryRequests = new Map();
  const uuid = () => crypto.randomUUID();
  const text = (selector, value) => { el(selector).textContent = value; };
  const notify = (value) => { status.textContent = value; status.dataset.tone = "info"; };
  const message = (error) => {
    status.textContent = (error.message || String(error)).replace(/^Error invoking remote method '[^']+': (?:Error: )?/, "");
    status.dataset.tone = "error";
  };
  const chosen = () => [...selected].sort();
  function update() {
    const count = selected.size, n = Number(form.elements.n.value);
    const validN = Number.isInteger(n) && n >= 1 && n <= 250;
    const purpose = options?.purposes[form.elements.purpose.value];
    text("[data-selected-count]", `${count}개 선택`);
    text("[data-briefing-summary]", `${form.elements.market.value === "KR" ? "한국" : "미국"} · ${count}개 종목 · ${validN ? `최근 ${n}거래일` : "기간 미선택"} · ${form.elements.purpose.value === "pre_market" ? "장전" : "장후"}`);
    text("[data-purpose-hint]", purpose ? `${purpose.reason} (${options.timezone === "Asia/Seoul" ? "한국 시간" : "뉴욕 시간"})` : "생성 가능 시간을 확인하고 있습니다.");
    const reason = loading ? "관심종목과 설정을 불러오는 중입니다." : !options ? "목록을 불러오지 못했습니다. 새로고침해 주세요."
      : !options.symbols.length ? "관심종목을 등록하면 브리핑을 만들 수 있습니다." : !count ? "분석할 관심종목을 하나 이상 선택해 주세요."
      : count > 30 ? "한 번에 30개까지 선택할 수 있습니다." : !validN ? "차트 관찰기간을 입력해 주세요."
      : !options.prompt_ready ? "분석 지침 준비가 필요합니다. 운영자가 지침을 적용한 뒤 생성할 수 있습니다."
      : !purpose?.available ? purpose?.reason || "지금은 생성할 수 없습니다." : "";
    submit.disabled = busy || Boolean(reason);
    submit.textContent = busy ? "브리핑을 준비하고 있습니다…" : "선택한 종목으로 브리핑 만들기";
    text("[data-generation-help]", reason);
    text("[data-delivery-summary]", saved?.kakao_enabled ? "결과를 이 화면에 보관하고, 저장된 수신 설정에 따라 카카오 전달을 시도합니다." : "결과는 이 화면에 보관됩니다. 현재 카카오 수신은 꺼져 있습니다.");
    el("[data-save-briefing]").disabled = busy || loading || !options || !count || count > 30 || !validN;
    root.querySelectorAll("[data-days]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.days) === n)));
  }
  function renderTargets() {
    targets.innerHTML = window.StockAgent.renderBriefingTargets(options?.symbols || [], selected, search.value);
    targets.querySelectorAll("input").forEach((input) => { input.disabled = busy; });
    update();
  }
  function setBusy(value) {
    busy = value;
    form.querySelectorAll("input,select,button").forEach((input) => { input.disabled = value; });
    update();
  }
  async function loadMarket(preserve = false) {
    if (busy) return;
    const version = ++loadVersion, market = form.elements.market.value;
    loading = true; update();
    try {
      const [settings, readiness] = await Promise.all([backend.briefingSettings(market), backend.briefingOptions(market)]);
      if (version !== loadVersion || form.elements.market.value !== market) return;
      const keep = preserve && loadedMarket === market;
      options = readiness; saved = settings;
      selected = new Set((keep ? chosen() : settings.symbols || []).filter((s) => readiness.symbols.includes(s)));
      if (!keep) {
        form.elements.n.value = settings.n || "";
        ["pre_market_enabled", "post_market_enabled", "kakao_enabled"].forEach((k) => { form.elements[k].checked = settings[k]; });
        if (!readiness.purposes[form.elements.purpose.value]?.available) {
          const available = Object.keys(readiness.purposes).find((p) => readiness.purposes[p].available);
          if (available) form.elements.purpose.value = available;
        }
        originalId = null; generationRequest = null; search.value = "";
      }
      loadedMarket = market;
      text("[data-saved-schedule]", `저장된 설정: ${settings.symbols ? `${settings.symbols.length}개 지정 종목` : "현재 시장의 전체 관심종목"} · ${settings.n ? `${settings.n}거래일` : "기간 미설정"} · 장전 ${settings.pre_market_enabled ? "켜짐" : "꺼짐"} / 장후 ${settings.post_market_enabled ? "켜짐" : "꺼짐"}`);
      text("[data-source-notice]", readiness.disclosure_configured ? "뉴스와 공식 공시를 함께 조회합니다. 수집 범위와 누락은 결과에 표시합니다." : "공식 공시 조회 설정이 아직 없습니다. 생성하면 차트·뉴스를 중심으로 분석하고 공시 누락을 표시합니다.");
      text("[data-kakao-hint]", `${readiness.kakao_connected ? "카카오 수신 연결됨" : "카카오로 받으려면 상단 ‘카카오 알림 연결’을 먼저 완료해 주세요."}${readiness.scheduler_enabled ? "" : " 현재 자동 실행 기능이 꺼져 있습니다."}`);
      renderTargets();
    } catch (error) { if (version === loadVersion) { options = null; message(error); } }
    finally { if (version === loadVersion) { loading = false; update(); } }
  }
  async function refresh(append = false) {
    if (loadingHistory) return;
    loadingHistory = true;
    try {
      const runs = await backend.listBriefings(append ? offset : 0);
      if (!append) { history.replaceChildren(); offset = 0; }
      runs.forEach((run) => {
        const button = document.createElement("button");
        button.type = "button";
        const labels = { preparing: "준비 중", completed: "완료", partial: "일부 자료로 완료", deferred: "자료 부족", failed: "생성 실패" };
        button.textContent = `${run.trade_date} · ${run.market === "KR" ? "한국" : "미국"} ${run.purpose === "pre_market" ? "장전" : "장후"}\n${run.context?.symbols?.length || 0}개 종목 · ${labels[run.status] || "브리핑 보기"}`;
        button.addEventListener("click", () => select(run.id).catch(message)); history.append(button);
      });
      offset += runs.length; more.hidden = runs.length < 30;
      if (!offset) history.textContent = "아직 브리핑이 없습니다. 위에서 종목을 선택해 첫 브리핑을 만들어보세요.";
    } finally { loadingHistory = false; }
  }
  async function select(id) {
    const version = ++detailVersion, run = await backend.briefingById(id);
    if (version !== detailVersion) return;
    currentRun = run; detail.innerHTML = window.StockAgent.renderBriefing(run);
    detail.querySelector("[data-redeliver]")?.addEventListener("click", async () => {
      if (busy) return;
      const unknown = run.delivery.status === "unknown";
      if (unknown && !window.confirm("이전 메시지가 이미 도착했을 수 있습니다. 중복 도착 가능성을 감수하고 다시 보낼까요?")) return;
      setBusy(true);
      if (!retryRequests.has(id)) retryRequests.set(id, uuid());
      try {
        await backend.redeliverBriefing(id, { request_id: retryRequests.get(id), acknowledge_unknown: unknown });
        retryRequests.delete(id); await select(id);
      } catch (error) { message(error); } finally { setBusy(false); }
    });
    detail.querySelector("[data-reanalyze]")?.addEventListener("click", async () => {
      if (busy) return;
      form.elements.market.value = run.market; await loadMarket();
      if (!options) return;
      selected = new Set((run.context.symbols || []).filter((s) => options.symbols.includes(s)));
      form.elements.n.value = run.context.n; form.elements.purpose.value = run.purpose;
      originalId = id; generationRequest = null; renderTargets();
      notify("이전 분석의 종목과 기간을 불러왔습니다. 현재 관심종목에 남아 있는 대상과 생성 가능 시간을 확인한 뒤 만들어 주세요.");
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  async function generate() {
    update();
    if (busy || submit.disabled || !form.reportValidity()) return;
    const shape = { market: form.elements.market.value, purpose: form.elements.purpose.value,
      n: Number(form.elements.n.value), symbols: chosen(), original_id: originalId };
    if (!generationRequest || generationRequest.shape !== JSON.stringify(shape)) generationRequest = { shape: JSON.stringify(shape), id: uuid() };
    setBusy(true);
    notify(`${shape.symbols.length}개 종목의 자료를 모아 분석하고 있습니다. 창을 유지해 주세요. 목록 새로고침으로 상태를 확인할 수 있습니다.`);
    try {
      const run = await backend.generateBriefing({ ...shape, request_id: generationRequest.id });
      await refresh(); await select(run.id);
      notify(run.failure_reason || (run.status === "preparing" ? "아직 분석 중입니다. 목록 새로고침으로 진행 상태를 확인하세요." : "브리핑이 준비됐습니다. 아래에서 종목별 결과를 확인하세요."));
      if (run.status !== "preparing") { generationRequest = null; originalId = null; }
      detail.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) { message(error); } finally { setBusy(false); }
  }
  form.addEventListener("submit", (event) => { event.preventDefault(); return generate(); });
  form.addEventListener("input", update); form.addEventListener("change", update);
  form.elements.market.addEventListener("change", () => loadMarket());
  targets.addEventListener("change", (event) => {
    const symbol = event.target.dataset.targetSymbol;
    if (busy || !symbol || !options?.symbols.includes(symbol)) return;
    if (event.target.checked) {
      if (selected.size >= 30) { event.target.checked = false; message(new Error("한 번에 최대 30개까지 선택할 수 있습니다.")); return; }
      selected.add(symbol);
    } else selected.delete(symbol);
    event.target.closest("label")?.classList.toggle("is-selected", event.target.checked); update();
  });
  search.addEventListener("input", renderTargets);
  el("[data-select-all]").addEventListener("click", () => {
    if (!options || busy) return;
    if (options.symbols.length > 30) { message(new Error("관심종목이 30개를 넘습니다. 분석할 종목을 직접 선택해 주세요.")); return; }
    selected = new Set(options.symbols); renderTargets();
  });
  el("[data-clear-selection]").addEventListener("click", () => { selected.clear(); renderTargets(); });
  el("[data-manage-watchlist]").addEventListener("click", () => window.StockAgent.showView("watchlist-view"));
  root.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => { form.elements.n.value = b.dataset.days; update(); }));
  el("[data-save-briefing]").addEventListener("click", async () => {
    if (busy || loading || !options || !selected.size || !form.reportValidity()) return;
    const body = { n: Number(form.elements.n.value), symbols: chosen(), pre_market_enabled: form.elements.pre_market_enabled.checked,
      post_market_enabled: form.elements.post_market_enabled.checked, kakao_enabled: form.elements.kakao_enabled.checked };
    setBusy(true);
    try { await backend.saveBriefingSettings(form.elements.market.value, body); saved = body; notify("선택한 종목과 기간, 자동 제공·수신 설정을 저장했습니다."); }
    catch (error) { message(error); }
    finally { setBusy(false); await loadMarket(true); }
  });
  el("[data-refresh-briefing]").addEventListener("click", async () => {
    try { await Promise.all([loadMarket(true), refresh()]); if (currentRun) await select(currentRun.id); } catch (error) { message(error); }
  });
  more.addEventListener("click", () => refresh(true).catch(message));
  const onView = (event) => {
    if (!root.isConnected) { document.removeEventListener("stock-agent:view", onView); return; }
    if (event.detail === "briefing-view") loadMarket(true);
  };
  document.addEventListener("stock-agent:view", onView);
  return { load: () => Promise.all([loadMarket(), refresh()]).catch(message) };
}
window.StockAgent = { ...window.StockAgent, createBriefingController };
})();
