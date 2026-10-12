(() => {
const { AlertConditionItem } = window.StockAgent;

function AlertConditionsPanel() {
  return `
    <section id="alert-conditions-section" class="card alert-conditions-card">
      <div class="section-heading alert-heading">
        <div><h2>사용자 알림 조건</h2><p>내 관심종목에서 대상을 고르고 알림 조건을 작성하세요.</p></div>
      </div>
      <form id="alert-condition-form" class="alert-condition-form">
        <div id="watchlist-security-picker"></div>
        <textarea id="alert-rule-input" placeholder="예: 삼성전자 반도체 수요 관련 부정적 뉴스가 있으면 알려줘" aria-label="사용자 알림 조건"></textarea>
        <button class="primary-button" type="submit">검증 후 저장</button>
      </form>
      <p id="alert-condition-status" class="condition-status" aria-live="polite"></p>
      <div id="alert-condition-list" class="alert-condition-list"></div>
    </section>`;
}

function renderAlertConditions(conditions, onDelete) {
  const list = document.querySelector("#alert-condition-list");
  if (!conditions.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "저장된 사용자 알림 조건이 없습니다.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...conditions.map((condition) => AlertConditionItem(condition, onDelete)));
}

window.StockAgent = { ...window.StockAgent, AlertConditionsPanel, renderAlertConditions };
})();
