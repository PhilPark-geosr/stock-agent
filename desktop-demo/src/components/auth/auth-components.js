(() => {
function OAuthLoginButton({ provider, label, disabled = false }) {
  return `<button class="oauth-login-button oauth-${provider}" type="button" data-auth-login ${disabled ? "disabled" : ""}>
    <span class="oauth-mark" aria-hidden="true">${provider === "kakao" ? "K" : "↗"}</span>
    <span>${label}</span>
  </button>`;
}

function KakaoLoginButton(disabled = false) {
  return OAuthLoginButton({ provider: "kakao", label: disabled ? "카카오 로그인 진행 중…" : "카카오로 로그인", disabled });
}

function LoginPage({ status, error }) {
  const authenticating = status === "authenticating";
  const restoring = status === "restoring";
  return `<main class="login-page">
    <section class="login-card" aria-labelledby="login-title">
      <div class="login-brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M7 20l6-7 5 4 8-10"/><path d="M21 7h5v5"/></svg></span></div>
      <p class="eyebrow">STOCK AGENT DESKTOP</p>
      <h1 id="login-title">내 관심 종목을 이어서 분석하세요</h1>
      <p class="login-description">로그인하면 관심 종목과 알림 조건을 내 계정 범위에서 안전하게 관리할 수 있습니다.</p>
      ${restoring ? '<p class="login-progress" role="status">저장된 세션을 확인하고 있습니다…</p>' : KakaoLoginButton(authenticating)}
      ${error ? `<p class="login-error" role="alert">${escapeHtml(error)}</p>` : ""}
      <p class="login-footnote">로그인은 기본 브라우저에서 진행됩니다.</p>
    </section>
  </main>`;
}

function AccountMenu() {
  return `<div class="account-menu">
    <span class="account-avatar" aria-hidden="true">K</span>
    <span><strong id="account-provider">로그인됨</strong><small id="account-id"></small></span>
    <button id="logout-button" class="text-button" type="button">로그아웃</button>
  </div>`;
}

function AppRoot() {
  return `<div id="auth-view"></div><div id="application-view" hidden></div>`;
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

window.StockAgent = { ...window.StockAgent, AccountMenu, AppRoot, KakaoLoginButton, LoginPage, OAuthLoginButton };
})();
