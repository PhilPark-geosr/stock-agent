(() => {
function MetricsPanel() {
  return `<section class="card metrics-card">
    <div class="metric"><span>거래량 비율</span><strong id="volume-ratio"></strong><small>MarketIndicators</small></div>
    <div class="metric"><span>20일 저점</span><strong id="low-price"></strong><small>low_20</small></div>
    <div class="metric"><span>20일 고점</span><strong id="high-price"></strong><small>high_20</small></div>
    <div class="metric"><span>알림 조건</span><strong id="matched-alerts"></strong><small>평가 중단</small></div>
  </section>`;
}

window.StockAgent = { ...window.StockAgent, MetricsPanel };
})();
