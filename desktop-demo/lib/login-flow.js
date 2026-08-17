const crypto = require("crypto");

function challengeFor(verifier) {
  return crypto.createHash("sha256").update(verifier).digest("base64url");
}

function defaultVerifier() {
  return crypto.randomBytes(32).toString("base64url");
}

function createLoginFlow({
  request,
  openExternal,
  sessionStore,
  createVerifier = defaultVerifier,
  wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
  now = () => new Date()
}) {
  let activeLogin = null;

  async function performLogin() {
    const verifier = createVerifier();
    const started = await request("/auth/login-attempts", {
      method: "POST",
      body: { verifier_challenge: challengeFor(verifier) }
    });
    const { attempt_id: attemptId, authorization_url: authorizationUrl, expires_at: expiresAt } = started.payload;
    await openExternal(authorizationUrl);

    const deadline = new Date(expiresAt);
    while (now() < deadline) {
      await wait(1000);
      const exchanged = await request(`/auth/login-attempts/${encodeURIComponent(attemptId)}/exchange`, {
        method: "POST",
        body: { verifier }
      });
      if (exchanged.status === 202) continue;
      await sessionStore.save(exchanged.payload.session_token);
      return exchanged.payload.account;
    }
    throw new Error("로그인 요청이 만료되었습니다. 다시 시도해 주세요.");
  }

  function login() {
    if (activeLogin) return activeLogin;
    activeLogin = performLogin().finally(() => { activeLogin = null; });
    return activeLogin;
  }

  return { login };
}

module.exports = { challengeFor, createLoginFlow };
