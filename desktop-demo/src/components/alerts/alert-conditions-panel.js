(() => {
const { AlertConditionItem } = window.StockAgent;

function AlertConditionsPanel() {
  return `
    <section id="alert-conditions-section" class="card alert-conditions-card">
      <div class="section-heading alert-heading">
        <div><h2>사용자 알림 조건</h2><p>API: /alert-conditions</p></div>
        <button id="kakao-login-button" class="text-button" type="button">카카오 로그인</button>
      </div>
      <form id="alert-condition-form" class="alert-condition-form">
        <input id="alert-symbol-input" placeholder="종목 코드" aria-label="알림 조건 종목 코드">
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
