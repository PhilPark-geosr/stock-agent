(() => {
const { Sidebar, Topbar, DialogRoot } = window.StockAgent;

function AppShell(content) {
  return `
    <div class="app-frame">
      ${Sidebar()}
      <main class="main-content">
        ${Topbar()}
        ${content}
      </main>
    </div>
    <div id="toast" class="toast" role="status" aria-live="polite"></div>
    ${DialogRoot()}`;
}

window.StockAgent = { ...window.StockAgent, AppShell };
})();
