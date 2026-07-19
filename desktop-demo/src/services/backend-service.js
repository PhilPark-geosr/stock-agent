(() => {
function createBackendService() {
  return window.desktop?.backend || null;
}

window.StockAgent = { ...window.StockAgent, createBackendService };
})();
