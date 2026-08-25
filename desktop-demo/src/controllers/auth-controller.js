(function authControllerModule(root, factory) {
  const exports = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  if (root) root.StockAgent = { ...root.StockAgent, ...exports };
})(typeof window === "undefined" ? null : window, () => {
  function createAuthController({ auth, render, initializeApplication, resetApplication = () => {} }) {
    let loginPromise = null;
    let initialized = false;
    let account = null;

    async function showAuthenticated(nextAccount) {
      account = nextAccount;
      render({ status: "authenticated", account });
      if (!initialized) {
        initialized = true;
        await initializeApplication(account);
      }
      return account;
    }

    async function start() {
      render({ status: "restoring", account: null });
      const restored = await auth.restore();
      if (restored) return showAuthenticated(restored);
      account = null;
      render({ status: "anonymous", account: null });
      return null;
    }

    function login() {
      if (loginPromise) return loginPromise;
      render({ status: "authenticating", account: null });
      loginPromise = auth.login()
        .then(showAuthenticated)
        .catch((error) => {
          account = null;
          render({ status: "anonymous", account: null, error: error.message });
          throw error;
        })
        .finally(() => { loginPromise = null; });
      return loginPromise;
    }

    async function logout() {
      await auth.logout();
      account = null;
      initialized = false;
      resetApplication();
      render({ status: "anonymous", account: null });
    }

    const unsubscribe = auth.onExpired?.(() => {
      account = null;
      initialized = false;
      resetApplication();
      render({ status: "anonymous", account: null, error: "세션이 만료되었습니다. 다시 로그인해 주세요." });
    });

    return { start, login, logout, dispose: () => unsubscribe?.() };
  }

  return { createAuthController };
});
