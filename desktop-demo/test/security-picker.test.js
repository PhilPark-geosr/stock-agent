const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const tick = () => new Promise(setImmediate);

function setup(searchSecurities) {
  const node = () => ({ value: "", dataset: {}, listeners: {}, children: [],
    addEventListener(name, fn) { this.listeners[name] = fn; },
    setAttribute(name, value) { this[name] = value; },
    replaceChildren() { this.children = []; }, append(child) { this.children.push(child); },
    querySelectorAll() { return this.children; } });
  const elements = Object.fromEntries(["query", "country", "sort", "status", "results", "selection", "more", "refresh", "clear"].map(k => [k, node()]));
  elements.sort.value = "relevance";
  const root = { isConnected: true, querySelector: key => elements[key.slice(15, -1)] };
  const context = vm.createContext({ window: { StockAgent: {} }, document: { createElement: node }, setTimeout, clearTimeout });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/components/ui/security-picker.js"), "utf8"), context);
  const chosen = [];
  const picker = context.window.StockAgent.createSecurityPicker({root, backend: {searchSecurities}, scope: "catalog", onSelect: row => chosen.push(row)});
  return {picker, elements, chosen};
}
const item = (key) => ({key, symbol:key, name:key, country:"US", status:"active", selectable:true, note:""});
const result = (items) => ({items, total:items.length, next_cursor:null, catalog:[]});

test("a single result needs explicit selection; sorting preserves its identity", async () => {
  const s = setup(async () => result([item("AAPL")])); await tick();
  assert.equal(s.picker.selection(), null);
  s.elements.results.children[0].listeners.click();
  assert.equal(s.picker.selection().key, "AAPL");
  s.elements.sort.value = "name_asc"; await s.elements.sort.listeners.change();
  assert.equal(s.picker.selection().key, "AAPL");
  assert.equal(s.elements.results.children[0]["aria-pressed"], "true");
});

test("out of order search responses cannot replace the latest results", async () => {
  const pending = [];
  const s = setup(() => new Promise(resolve => pending.push(resolve)));
  const newer = s.picker.refresh();
  pending[1](result([item("NEW")])); await newer;
  pending[0](result([item("OLD")])); await tick();
  assert.equal(s.elements.results.children[0].dataset.key, "NEW");
});

test("typing invalidates a selection and clears stale clickable results immediately", async () => {
  const s = setup(async () => result([item("AAPL")])); await tick();
  s.elements.results.children[0].listeners.click();
  s.elements.query.value = "MSFT";
  s.elements.query.listeners.input();
  assert.equal(s.picker.selection(), null);
  assert.equal(s.elements.results.children.length, 0);
  s.elements.query.listeners.keydown({key:"Enter", preventDefault(){}}); await tick();
});
