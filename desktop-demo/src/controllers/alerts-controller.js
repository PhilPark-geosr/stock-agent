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
    document.querySelector("#alert-condition-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const symbolInput = document.querySelector("#alert-symbol-input");
      const ruleInput = document.querySelector("#alert-rule-input");
      const status = document.querySelector("#alert-condition-status");
      const symbol = (symbolInput.value.trim() || state.selectedSymbol || "").toUpperCase();
      const rule = ruleInput.value.trim();
      if (!symbol || !rule) {
        status.textContent = "종목 코드와 알림 조건을 입력하세요.";
        return;
      }
      status.textContent = "Gemini로 조건을 검증하고 있습니다...";
      try {
        const condition = await backend.addAlertCondition(symbol, rule);
        ruleInput.value = "";
        status.textContent = condition.validation_summary;
        await loadAlertConditions();
        showToast(`알림 조건 #${condition.id}을 저장했습니다.`);
      } catch (error) {
        console.error("Alert condition validation failed", error);
        status.textContent = "저장 실패";
        showDialog({
          eyebrow: "조건 검증 실패",
          title: "알림 조건을 저장하지 못했습니다",
          message: "모델이 입력한 조건을 검증하지 못했습니다. 조건을 조금 더 구체적으로 작성한 뒤 다시 시도해 주세요."
        });
      }
    });
  }

  return { bindAlertsEvents, deleteAlertCondition, loadAlertConditions };
}

window.StockAgent = { ...window.StockAgent, createAlertsController };
})();
