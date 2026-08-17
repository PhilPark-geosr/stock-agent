const test = require("node:test");
const assert = require("node:assert/strict");

const { createLoginFlow, challengeFor } = require("../lib/login-flow.js");

test("opens provider authorization and polls a one-time exchange without exposing the token", async () => {
  const calls = [];
  let exchanges = 0;
  let saved;
  const flow = createLoginFlow({
    request: async (requestPath, options) => {
      calls.push({ requestPath, options });
      if (requestPath === "/auth/login-attempts") {
        return { status: 201, payload: { attempt_id: "a1", authorization_url: "https://kauth.test/login", expires_at: "2099-01-01T00:00:00Z" } };
      }
      exchanges += 1;
      if (exchanges === 1) return { status: 202, payload: null };
      return { status: 200, payload: { session_token: "secret", account: { id: "u1", login_provider: "kakao" } } };
    },
    openExternal: async (url) => { calls.push({ openExternal: url }); },
    sessionStore: { save: async (token) => { saved = token; } },
    createVerifier: () => "verifier",
    wait: async () => {},
    now: () => new Date("2026-01-01T00:00:00Z")
  });

  const account = await flow.login();

  assert.deepEqual(account, { id: "u1", login_provider: "kakao" });
  assert.equal(saved, "secret");
  assert.equal(calls[0].options.body.verifier_challenge, challengeFor("verifier"));
  assert.equal(calls[1].openExternal, "https://kauth.test/login");
  assert.equal(exchanges, 2);
  assert.equal("session_token" in account, false);
});

test("expires the local polling loop at the server deadline", async () => {
  const flow = createLoginFlow({
    request: async (requestPath) => requestPath === "/auth/login-attempts"
      ? { status: 201, payload: { attempt_id: "a1", authorization_url: "https://kauth.test/login", expires_at: "2026-01-01T00:00:00Z" } }
      : { status: 202, payload: null },
    openExternal: async () => {},
    sessionStore: { save: async () => {} },
    createVerifier: () => "verifier",
    wait: async () => {},
    now: () => new Date("2026-01-01T00:00:01Z")
  });

  await assert.rejects(() => flow.login(), /만료/);
});
