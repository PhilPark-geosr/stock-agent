(() => {
function createNotificationController({
  notifications,
  showToast,
  getButton = () => document.querySelector("#notification-connection-button")
}) {
  function render(connection) {
    const target = getButton();
    if (!target) return;
    target.disabled = false;
    target.dataset.connected = String(Boolean(connection.connected));
    target.textContent = connection.connected ? "카카오 알림 연결 해제" : "카카오 알림 연결";
  }

  function renderUnavailable() {
    const target = getButton();
    if (!target) return;
    target.disabled = true;
    target.dataset.connected = "false";
    target.textContent = "카카오 알림 설정 필요";
  }

  function renderPending() {
    const target = getButton();
    if (!target) return;
    target.disabled = true;
    target.textContent = "카카오 알림 연결 중…";
  }

  function renderError() {
    const target = getButton();
    if (!target) return;
    target.disabled = false;
    target.dataset.connected = "false";
    target.textContent = "카카오 알림 연결 오류";
  }

  async function refresh() {
    try {
      const status = await notifications.status();
      render(status);
      return status;
    } catch {
      const unavailable = { available: false, connected: false };
      renderUnavailable();
      return unavailable;
    }
  }

  async function toggle() {
    const connected = getButton()?.dataset.connected === "true";
    if (connected) {
      const result = await notifications.disconnect();
      render(result);
      showToast("카카오 알림 연결을 해제했습니다.");
      return result;
    }

    renderPending();
    try {
      const result = await notifications.connect();
      render(result);
      showToast("카카오 알림 연결이 완료되었습니다.");
      return result;
    } catch (error) {
      renderError();
      throw error;
    }
  }

  function bind() {
    getButton()?.addEventListener("click", () =>
      toggle().catch((error) => showToast(error.message))
    );
  }

  return { bind, refresh, toggle };
}

if (typeof window !== "undefined") {
  window.StockAgent = { ...window.StockAgent, createNotificationController };
}
if (typeof module !== "undefined") {
  module.exports = { createNotificationController };
}
})();
