const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function loadState() {
  const context = vm.createContext({ window: {}, Date, Intl });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/state/app-state.js"), "utf8"), context);
  return context.window.StockAgent;
}

test("detail and history preserve the local session date independently of the UTC instant", () => {
  const app = loadState();
  const row = {
    id: 1, symbol: "005930.KS", analyzed_at: "2026-11-08T23:10:00Z",
    data_timestamp: "2026-11-05T15:00:00Z",
    chart_basis: { interval: "1d", session_date: "2026-11-06", finality: "unknown" },
  };
  app.state.selectedAnalysis = app.normalizeAnalysis(row);
  const history = app.normalizeHistoryItem(row);
  assert.match(history.time, /2026\. 11\. 9\..*KST/);
  assert.equal(history.time, app.state.selectedAnalysis.time);
  assert.equal(app.selectedStockView().dataTime, "2026-11-06 일봉 기준 · 시장 현지일");
  assert.equal(app.selectedStockView().priceLabel, "일봉 기준 가격");
  assert.equal(app.basisLabel(history.chartBasis), app.selectedStockView().dataTime);
});

test("legacy and invalid timestamp values do not become an invented session date", () => {
  const app = loadState();
  app.state.selectedAnalysis = app.normalizeAnalysis({
    id: 2, data_timestamp: "2026-11-06T00:00:00Z", analyzed_at: "2026-11-06T10:00:00",
  });
  assert.equal(app.selectedStockView().dataTime, "가격 기준 거래일 미확인");
  assert.equal(app.state.selectedAnalysis.time, "기록 시각 미확인");
  assert.equal(app.normalizeHistoryItem({ analyzed_at: "invalid" }).time, "기록 시각 미확인");
});

test("a late history response cannot replace the selected result and its basis", async () => {
  const app = loadState();
  const pending = new Map();
  const context = vm.createContext({ window: { StockAgent: app }, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/controllers/analysis-controller.js"), "utf8"), context);
  app.state.selectedSymbol = "AAPL";
  const controller = context.window.StockAgent.createAnalysisController({
    backend: { analysisById: (symbol, id) => new Promise(resolve => pending.set(id, resolve)) },
    renderScreen() {}, showToast() {}, showDialog() {}, showView() {},
  });
  const first = controller.selectAnalysis(1);
  const second = controller.selectAnalysis(2);
  pending.get(2)({ id: 2, symbol: "AAPL", chart_basis: { interval: "1d", session_date: "2026-11-06" } });
  await second;
  pending.get(1)({ id: 1, symbol: "AAPL", chart_basis: { interval: "1d", session_date: "2026-11-05" } });
  await first;
  assert.equal(app.state.selectedAnalysis.id, 2);
  assert.equal(app.state.selectedAnalysis.chartBasis.session_date, "2026-11-06");
});

for (const [phase, label] of [["during_session", "장중 기준"], ["after_session", "정규장 종료 후 수집"], ["boundary", "장 마감 경계에서 수집"]]) {
  test(`saved ${phase} has the same meaning in detail and history`, () => {
    const app = loadState();
    const row = { id: 1, chart_basis: { interval: "1d", session_date: "2026-11-06", collection_phase: phase, collected_at: "2026-11-06T06:31:00Z" } };
    app.state.selectedAnalysis = app.normalizeAnalysis(row);
    assert.equal(app.selectedStockView().phaseLabel, label);
    assert.equal(app.phaseLabel(app.normalizeHistoryItem(row).chartBasis), label);
    assert.match(app.selectedStockView().collectedTime, /가격 수집 완료.*KST/);
    if (phase === "after_session") assert.match(app.selectedStockView().finalityLabel, /마감 가격 반영은 확인되지/);
  });
}

test("unknown phase explains a missing exchange calendar", () => {
  const app = loadState();
  assert.equal(app.phaseExplanation({ phase_reason: "calendar_unavailable" }), "거래소 일정을 확인하지 못했습니다.");
});
