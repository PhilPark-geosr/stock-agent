const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { renderBriefingTargets } = require("../src/components/briefings/briefing-panel");
const tick = () => new Promise(setImmediate);

function fixture(backend) {
  const element = () => ({ value: "", checked: false, textContent: "", listeners: {}, children: [], dataset: {},
    addEventListener(name, action) { this.listeners[name] = action; },
    replaceChildren() { this.children = []; }, append(child) { this.children.push(child); },
    querySelector() { return null; }, querySelectorAll() { return []; }, scrollIntoView() {}, setAttribute() {} });
  const form = element();
  form.elements = Object.fromEntries(["market", "n", "purpose", "pre_market_enabled", "post_market_enabled", "kakao_enabled"].map(k => [k, element()]));
  form.elements.market.value = "KR"; form.elements.n.value = "2"; form.elements.purpose.value = "pre_market";
  form.reportValidity = () => true;
  const elements = { form, "[data-briefing-status]": element(), "[data-briefing-history]": element(),
    "[data-briefing-detail]": element(), "[data-more-briefings]": element(), "[data-save-briefing]": element(), "[data-refresh-briefing]": element() };
  for (const name of ["briefing-targets", "target-search", "generate-briefing", "selected-count", "briefing-summary", "purpose-hint", "generation-help", "delivery-summary", "saved-schedule", "source-notice", "kakao-hint", "select-all", "clear-selection", "manage-watchlist"])
    elements[`[data-${name}]`] = element();
  const root = { querySelector: (name) => elements[name], querySelectorAll: () => [], isConnected: true };
  backend.briefingOptions ||= async () => ({ symbols: ["005930.KS", "000660.KS"], prompt_ready: true, timezone: "Asia/Seoul",
    purposes: { pre_market: { available: true, reason: "개장 전" }, post_market: { available: false, reason: "마감 후" } } });
  let sequence = 0;
  const browser = vm.createContext({ document: { querySelector: () => root, createElement: element, addEventListener() {}, removeEventListener() {} },
    crypto: { randomUUID: () => `request-${++sequence}` }, window: { StockAgent: { renderBriefingTargets, renderBriefing: () => "<p>test</p>" } } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/controllers/briefing-controller.js"), "utf8"), browser);
  const controller = browser.window.StockAgent.createBriefingController({ backend });
  return { controller, elements, form, submit: () => form.listeners.submit({ preventDefault() {} }),
    choose: (symbol, checked = true) => elements["[data-briefing-targets]"].listeners.change({ target: { dataset: { targetSymbol: symbol }, checked, closest: () => null } }) };
}

test("generation blocks double clicks and keeps request identity after a lost response", async () => {
  const requests = [];
  let reject;
  const run = { id: "run", status: "completed" };
  const backend = { briefingSettings: async () => ({ n: 2 }), listBriefings: async () => [], briefingById: async () => run,
    generateBriefing: (body) => { requests.push(body); return requests.length === 1 ? new Promise((_, fail) => { reject = fail; }) : Promise.resolve(run); } };
  const s = fixture(backend);
  await s.controller.load();
  s.choose("005930.KS");
  s.submit(); s.submit();
  assert.equal(requests.length, 1);
  reject(new Error("connection lost")); await tick();
  s.submit(); await tick();
  assert.equal(requests.length, 2);
  assert.equal(requests[0].request_id, requests[1].request_id);
  assert.deepEqual(Array.from(requests[0].symbols), ["005930.KS"]);
  s.submit(); await tick();
  assert.notEqual(requests[1].request_id, requests[2].request_id);
});

test("empty selection blocks generation and saved automation remains separate from manual selection", async () => {
  const generated = [], saved = [];
  const backend = { briefingSettings: async () => ({ n: 20, symbols: ["000660.KS"], pre_market_enabled: true }),
    listBriefings: async () => [], briefingById: async () => ({id: "one", status: "completed"}),
    generateBriefing: async (body) => { generated.push(body); return {id: "one", status: "completed"}; },
    saveBriefingSettings: async (market, body) => saved.push(body) };
  const s = fixture(backend); await s.controller.load();
  await s.elements["[data-clear-selection]"].listeners.click();
  await s.submit(); assert.equal(generated.length, 0);
  s.choose("005930.KS"); await s.submit();
  assert.deepEqual(Array.from(generated[0].symbols), ["005930.KS"]);
  assert.equal(saved.length, 0);
  await s.elements["[data-save-briefing]"].listeners.click();
  assert.deepEqual(Array.from(saved[0].symbols), ["005930.KS"]);
});

test("unsupported or stale target events cannot add hidden symbols", async () => {
  const generated = [];
  const s = fixture({briefingSettings: async () => ({n: 2}), listBriefings: async () => [],
    generateBriefing: async (body) => { generated.push(body); return {id: "one", status: "completed"}; },
    briefingById: async () => ({id: "one"})});
  await s.controller.load(); s.choose("OTHER-USERS-SYMBOL"); await s.submit();
  assert.equal(generated.length, 0);
});

test("older briefing pages append without losing current history", async () => {
  const offsets = [];
  const backend = { briefingSettings: async () => ({ n: 2 }), listBriefings: async (offset) => {
    offsets.push(offset); return Array.from({length: offset ? 1 : 30}, (_, i) => ({ id: `${offset+i}`, trade_date: "2026-09-21", market: "KR", purpose: "pre_market" })); } };
  const s = fixture(backend);
  await s.controller.load();
  assert.equal(s.elements["[data-more-briefings]"].hidden, false);
  await s.elements["[data-more-briefings]"].listeners.click();
  assert.deepEqual(offsets, [0, 30]);
  assert.equal(s.elements["[data-briefing-history]"].children.length, 31);
  assert.equal(s.elements["[data-more-briefings]"].hidden, true);
});
