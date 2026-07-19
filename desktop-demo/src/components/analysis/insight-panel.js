(() => {
function InsightPanel(title, source, id, isRisk = false) {
  return `<article class="card insight-card"><div class="section-heading"><h2>${title}</h2><span>${source}</span></div><ul id="${id}" class="insight-list${isRisk ? " risk-list" : ""}"></ul></article>`;
}

window.StockAgent = { ...window.StockAgent, InsightPanel };
})();
