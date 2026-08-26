const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createNotificationController } = require("../src/controllers/notification-controller");

function button() {
  return { dataset: {}, disabled: false, textContent: "", addEventListener() {} };
}

test("browser renderer can consume the notification controller global", () => {
  const controllerSource = fs.readFileSync(
    path.join(__dirname, "../src/controllers/notification-controller.js"),
    "utf8"
  );
  const browser = vm.createContext({ window: { StockAgent: {} } });

  vm.runInContext(controllerSource, browser, { filename: "notification-controller.js" });

  assert.doesNotThrow(() =>
    vm.runInContext(
      "const { createNotificationController } = window.StockAgent;",
      browser,
      { filename: "renderer.js" }
    )
  );
  assert.equal(typeof browser.window.StockAgent.createNotificationController, "function");
});

test("notification status failure disables only notification setup", async () => {
  const target = button();
  const controller = createNotificationController({
    notifications: { status: async () => { throw new Error("notification token encryption is not configured"); } },
    showToast() {},
    getButton: () => target
  });

  const result = await controller.refresh();

  assert.deepEqual(result, { available: false, connected: false });
  assert.equal(target.disabled, true);
  assert.equal(target.textContent, "카카오 알림 설정 필요");
});

test("notification connect renders pending then connected", async () => {
  const target = button();
  let finish;
  const connecting = new Promise((resolve) => { finish = resolve; });
  const controller = createNotificationController({
    notifications: { connect: () => connecting }, showToast() {}, getButton: () => target
  });

  const result = controller.toggle();
  assert.equal(target.disabled, true);
  assert.equal(target.textContent, "카카오 알림 연결 중…");
  finish({ connected: true });
  await result;
  assert.equal(target.disabled, false);
  assert.equal(target.textContent, "카카오 알림 연결 해제");
});

test("notification connect renders an isolated error", async () => {
  const target = button();
  const controller = createNotificationController({
    notifications: { connect: async () => { throw new Error("provider unavailable"); } },
    showToast() {}, getButton: () => target
  });

  await assert.rejects(controller.toggle(), /provider unavailable/);
  assert.equal(target.disabled, false);
  assert.equal(target.textContent, "카카오 알림 연결 오류");
});
