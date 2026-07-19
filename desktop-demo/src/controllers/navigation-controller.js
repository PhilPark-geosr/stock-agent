(() => {
function showView(viewId) {
  document.querySelectorAll(".app-view").forEach((view) => {
    view.hidden = view.id !== viewId;
  });
  document.querySelectorAll(".flow-step").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function bindNavigationEvents() {
  document.querySelectorAll(".flow-step").forEach((button) => {
    button.addEventListener("click", () => {
      showView(button.dataset.view);
    });
  });
}

window.StockAgent = { ...window.StockAgent, bindNavigationEvents, showView };
})();
