const test = require("node:test");
const assert = require("node:assert/strict");

const { createSessionStore, createAuthenticatedRequester } = require("../lib/auth-session.js");

test("stores only encrypted token bytes and restores them", async () => {
  let persisted;
  const files = {
    writeFile: async (_path, value) => { persisted = value; },
    readFile: async () => persisted,
    unlink: async () => {}
  };
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(`encrypted:${value}`),
    decryptString: (value) => value.toString().replace("encrypted:", "")
  };
  const store = createSessionStore({ safeStorage, files, tokenPath: "token" });

  await store.save("secret-token");
  assert.equal(persisted.toString(), "encrypted:secret-token");
  assert.equal(await store.restore(), "secret-token");
});

test("keeps the token in memory without plaintext persistence when encryption is unavailable", async () => {
  let writes = 0;
  const store = createSessionStore({
    safeStorage: { isEncryptionAvailable: () => false },
    files: { writeFile: async () => { writes += 1; }, readFile: async () => null, unlink: async () => {} },
    tokenPath: "token"
  });

  await store.save("secret-token");

  assert.equal(writes, 0);
  assert.equal(store.current(), "secret-token");
  assert.equal(await store.restore(), null);
});

test("does not retain a token when encrypted persistence fails", async () => {
  const store = createSessionStore({
    safeStorage: { isEncryptionAvailable: () => true, encryptString: Buffer.from, decryptString: String },
    files: { writeFile: async () => { throw new Error("disk full"); }, readFile: async () => null, unlink: async () => {} },
    tokenPath: "token"
  });

  await assert.rejects(() => store.save("secret-token"), /disk full/);
  assert.equal(store.current(), null);
});

test("adds bearer in the main process and clears session on 401", async () => {
  let cleared = 0;
  let expired = 0;
  let headers;
  const requester = createAuthenticatedRequester({
    fetchImpl: async (_url, options) => {
      headers = options.headers;
      return { status: 401, ok: false, text: async () => JSON.stringify({ detail: "invalid session" }) };
    },
    getToken: () => "secret-token",
    clearToken: async () => { cleared += 1; },
    onExpired: () => { expired += 1; }
  });

  await assert.rejects(() => requester("https://api.test/watchlist", {}), /invalid session/);
  assert.equal(headers.Authorization, "Bearer secret-token");
  assert.equal(cleared, 1);
  assert.equal(expired, 1);
});
