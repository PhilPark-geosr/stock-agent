(() => {
const {
  state,
  emptyAnalysis,
  normalizeAnalysis,
  normalizeHistoryItem
} = window.StockAgent;

function analysisFailureDialog(error) {
  console.error("Analysis request failed", error);
  return {
    eyebrow: "분석 요청 실패",
    title: "분석을 완료하지 못했습니다",
    message: "모델 검증 또는 분석 처리 중 문제가 발생했습니다. 입력 조건과 백엔드 설정을 확인한 뒤 다시 시도해 주세요."
  };
}

function createAnalysisController({ backend, renderScreen, showToast, showDialog, showView }) {
  async function loadSelectedAnalysis() {
    const symbol = state.selectedSymbol;
    if (!symbol) return;
    document.querySelector("#scheduler-status").textContent = "데이터 조회 중";
    try {
      const [latestResult, historyResult] = await Promise.all([
        backend.latestAnalysis(symbol),
        backend.analysisHistory(symbol)
      ]);
      if (state.selectedSymbol !== symbol) return;
      const latest = normalizeAnalysis(latestResult);
      state.analysisDetails.set(latest.id, latest);
      state.selectedAnalysis = latest;
      state.analysisHistory = historyResult.map(normalizeHistoryItem);
      if (!state.analysisHistory.some((item) => item.id === latest.id)) {
        state.analysisHistory.unshift(latest);
      }
      document.querySelector("#scheduler-status").textContent = "대기";
      const stock = state.stocks.find((item) => item.symbol === symbol);
      if (stock) stock.alertStatus = latest.shouldAlert ? "전송 대상" : "조건 미충족";
      renderScreen();
    } catch (error) {
      if (state.selectedSymbol !== symbol) return;
      state.selectedAnalysis = emptyAnalysis(symbol);
      state.analysisHistory = [];
      document.querySelector("#scheduler-status").textContent = "조회 실패";
      renderScreen();
      console.error("Latest analysis lookup failed", error);
      showToast("분석 결과를 불러오지 못했습니다.");
    }
  }

  async function selectAnalysis(analysisId) {
    const cached = state.analysisDetails.get(analysisId);
    if (cached) {
      state.selectedAnalysis = cached;
      renderScreen();
      showView("analysis-view");
      return;
    }
    try {
      const result = await backend.analysisById(state.selectedSymbol, analysisId);
      const analysis = normalizeAnalysis(result);
      state.analysisDetails.set(analysisId, analysis);
      state.selectedAnalysis = analysis;
      renderScreen();
      showView("analysis-view");
    } catch (error) {
      console.error("Analysis history detail lookup failed", error);
      showToast("분석 이력을 불러오지 못했습니다.");
    }
  }

  function bindAnalysisEvents() {
    document.querySelector("#latest-button").addEventListener("click", async () => {
      await loadSelectedAnalysis();
      showView("analysis-view");
    });

    document.querySelector("#run-analysis-button").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      document.querySelector("#scheduler-status").textContent = "실행 중";
      try {
        const result = await backend.runScheduler();
        const analyzed = result.symbols_analyzed?.length || 0;
        const failed = result.symbols_failed?.length || 0;
        showToast(`스케줄러 완료: 성공 ${analyzed}개, 실패 ${failed}개`);
        if (failed > 0) {
          showDialog({
            eyebrow: "분석 일부 실패",
            title: "일부 종목 분석이 실패했습니다",
            message: "모델 검증 또는 데이터 수집 과정에서 일부 종목을 처리하지 못했습니다. 잠시 후 다시 실행해 주세요."
          });
        }
        await loadSelectedAnalysis();
      } catch (error) {
        document.querySelector("#scheduler-status").textContent = "실패";
        showDialog(analysisFailureDialog(error));
      } finally {
        button.disabled = false;
      }
    });
  }

  return { bindAnalysisEvents, loadSelectedAnalysis, selectAnalysis };
}

window.StockAgent = { ...window.StockAgent, createAnalysisController };
})();
