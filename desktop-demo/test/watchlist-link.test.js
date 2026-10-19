const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function fixture(confirmed, backend = {}) {
  const elements = Object.fromEntries(["#catalog-security-picker", "#search-form", "#search-input", "#add-symbol-form"].map(key => [key, {
    listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }
  }]));
  const item = { id: 7, symbol: "MSFT", name: "MSFT", security_id: null };
  const calls = [], notices = [];
  const selected = { symbol: "MSFT", name: "Microsoft", security_id: "security", country: "US", note: "NASDAQ", source_date: "2026-10-19" };
  const picker = { selection: () => selected, clear() {} };
  const state = { stocks: [item] };
  const context = vm.createContext({ document: { querySelector: key => elements[key] }, window: {
    confirm: message => { notices.push(message); return confirmed; },
    StockAgent: { state, errorMessage: error => error.message, createSecurityPicker: () => picker }
  }});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/controllers/watchlist-controller.js"), "utf8"), context);
  const controller = context.window.StockAgent.createWatchlistController({ backend: {
    linkWatchlist: async (...args) => calls.push(args),
    addWatchlist: async () => assert.fail("must not recreate a legacy subscription"),
    listWatchlist: async () => [{ ...item, security_id: "security" }], ...backend
  }, renderScreen() {}, showToast() {}, showView() {}, async loadSelectedAnalysis() {} });
  controller.bindWatchlistEvents();
  return { calls, notices, submit: () => elements["#add-symbol-form"].listeners.submit({ preventDefault() {} }) };
}

test("confirmation names candidate and preserves the exact subscription", async () => {
  const s = fixture(true); await s.submit();
  assert.deepEqual(s.calls, [[7, "MSFT", "security"]]);
  assert.match(s.notices[0], /Microsoft/);
  assert.match(s.notices[0], /NASDAQ/);
});

test("cancel does not link or add", async () => {
  const s = fixture(false); await s.submit(); assert.equal(s.calls.length, 0);
});

test("double submit is blocked while linking and failure permits retry of the same subscription", async () => {
  const calls = []; let reject;
  const s = fixture(true, { linkWatchlist: (...args) => {
    calls.push(args);
    return calls.length === 1 ? new Promise((_, fail) => { reject = fail; }) : Promise.resolve();
  }});
  const pending = s.submit(); await s.submit(); assert.equal(calls.length, 1);
  reject(new Error("lost response")); await pending; await s.submit();
  assert.deepEqual(calls, [[7, "MSFT", "security"], [7, "MSFT", "security"]]);
});
