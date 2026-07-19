(() => {
let previousFocus = null;

function DialogRoot() {
  return `
    <div id="app-dialog" class="dialog-backdrop" role="presentation" hidden>
      <section class="dialog-card" role="dialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby="dialog-message">
        <div class="dialog-icon" aria-hidden="true">!</div>
        <div class="dialog-content">
          <p id="dialog-eyebrow" class="dialog-eyebrow">알림</p>
          <h2 id="dialog-title"></h2>
          <p id="dialog-message"></p>
        </div>
        <div class="dialog-actions">
          <button id="dialog-close-button" class="primary-button" type="button">확인</button>
        </div>
      </section>
    </div>`;
}

function hideDialog() {
  document.querySelector("#app-dialog").hidden = true;
  previousFocus?.focus?.();
  previousFocus = null;
}

function showDialog({ title, message, eyebrow = "알림" }) {
  const dialog = document.querySelector("#app-dialog");
  previousFocus = document.activeElement;
  document.querySelector("#dialog-eyebrow").textContent = eyebrow;
  document.querySelector("#dialog-title").textContent = title;
  document.querySelector("#dialog-message").textContent = message;
  dialog.hidden = false;
  document.querySelector("#dialog-close-button").focus();
}

function bindDialogEvents() {
  const dialog = document.querySelector("#app-dialog");
  document.querySelector("#dialog-close-button").addEventListener("click", hideDialog);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) hideDialog();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !dialog.hidden) hideDialog();
    if (event.key !== "Tab" || dialog.hidden) return;
    const focusable = [...dialog.querySelectorAll("button")];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}

window.StockAgent = { ...window.StockAgent, DialogRoot, bindDialogEvents, showDialog, hideDialog };
})();
