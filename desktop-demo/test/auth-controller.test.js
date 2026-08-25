const test = require("node:test");
const assert = require("node:assert/strict");

const { createAuthController } = require("../src/controllers/auth-controller.js");

test("restores a valid session and initializes the application once", async () => {
  let initialized = 0;
  const views = [];
  const controller = createAuthController({
    auth: { restore: async () => ({ id: "u1", login_provider: "kakao" }) },
    render: (view) => views.push(view.status),
    initializeApplication: async () => { initialized += 1; }
  });

  await controller.start();
  await controller.start();

  assert.deepEqual(views, ["restoring", "authenticated", "restoring", "authenticated"]);
  assert.equal(initialized, 1);
});

test("blocks duplicate login clicks and initializes once after success", async () => {
  let resolveLogin;
  let loginCalls = 0;
  let initialized = 0;
  const loginResult = new Promise((resolve) => { resolveLogin = resolve; });
  const controller = createAuthController({
    auth: {
      restore: async () => null,
      login: async () => { loginCalls += 1; return loginResult; }
    },
    render: () => {},
    initializeApplication: async () => { initialized += 1; }
  });

  const first = controller.login();
  const second = controller.login();
  resolveLogin({ id: "u1", login_provider: "kakao" });
  await Promise.all([first, second]);

  assert.equal(loginCalls, 1);
  assert.equal(initialized, 1);
});

test("expiration and logout return to the login screen", async () => {
  let expirationHandler;
  let logoutCalls = 0;
  const views = [];
  const controller = createAuthController({
    auth: {
      restore: async () => ({ id: "u1", login_provider: "kakao" }),
      logout: async () => { logoutCalls += 1; },
      onExpired: (handler) => { expirationHandler = handler; return () => {}; }
    },
    render: (view) => views.push(view.status),
    initializeApplication: async () => {}
  });

  await controller.start();
  expirationHandler();
  await controller.logout();

  assert.equal(logoutCalls, 1);
  assert.deepEqual(views.slice(-2), ["anonymous", "anonymous"]);
});

test("initializes a fresh application after logout and another account login", async () => {
  let initialized = 0;
  let resets = 0;
  const accounts = [{ id: "u1" }, { id: "u2" }];
  const controller = createAuthController({
    auth: { login: async () => accounts.shift(), logout: async () => {} },
    render: () => {},
    initializeApplication: async () => { initialized += 1; },
    resetApplication: () => { resets += 1; }
  });

  await controller.login();
  await controller.logout();
  await controller.login();

  assert.equal(initialized, 2);
  assert.equal(resets, 1);
});
