(() => {
const { state, errorMessage } = window.StockAgent;

function createAlertsController({ backend, showToast, showDialog, renderAlertConditions }) {
  async function loadAlertConditions() {
    state.alertConditions = await backend.listAlertConditions();
    renderAlertConditions(state.alertConditions, deleteAlertCondition);
  }

  async function deleteAlertCondition(conditionId) {
    try {
      await backend.deleteAlertCondition(conditionId);
      showToast(`알림 조건 #${conditionId}을 삭제했습니다.`);
      await loadAlertConditions();
    } catch (error) {
      showToast(`알림 조건 삭제 실패: ${errorMessage(error)}`);
    }
  }

  function bindAlertsEvents() {
    const picker = window.StockAgent.createSecurityPicker({ root: document.querySelector("#watchlist-security-picker"), backend, scope: "watchlist" });
    document.querySelector("#alert-condition-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const selected = picker.selection();
      const ruleInput = document.querySelector("#alert-rule-input");
      const status = document.querySelector("#alert-condition-status");
      const symbol = selected?.symbol;
      const rule = ruleInput.value.trim();
      if (!symbol || !rule) {
        status.textContent = "내 관심종목에서 대상을 선택하고 알림 조건을 입력하세요.";
        return;
      }
      status.textContent = "Gemini로 조건을 검증하고 있습니다...";
      try {
        const condition = await backend.addAlertCondition(symbol, rule, selected.subscription_id);
        ruleInput.value = "";
        status.textContent = condition.validation_summary;
        await loadAlertConditions();
        showToast(`알림 조건 #${condition.id}을 저장했습니다.`);
      } catch (error) {
        console.error("Alert condition validation failed", error);
        status.textContent = `저장 실패: ${errorMessage(error)}`;
        showDialog({
          eyebrow: "조건 검증 실패",
          title: "알림 조건을 저장하지 못했습니다",
          message: errorMessage(error)
        });
      }
    });
  }

  return { bindAlertsEvents, deleteAlertCondition, loadAlertConditions };
}

window.StockAgent = { ...window.StockAgent, createAlertsController };
})();
