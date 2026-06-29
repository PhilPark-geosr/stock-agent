const {
  AppShell,
  showToast,
  WatchlistPanel,
  renderWatchlist,
  AnalysisWorkspace,
  renderAnalysis,
  renderHistory
} = window.StockAgent;

const stockData = [
  {
    symbol: "005930.KS",
    name: "삼성전자",
    price: 74800,
    change: 2.18,
    volumeRatio: "1.8x",
    low20: "72,500",
    high20: "76,200",
    alertStatus: "전송 대상",
    alertDetail: "조건 충족, 카카오 발송 전",
    matchedAlerts: ["거래량 급증", "이동평균 상향 돌파"],
    dataTime: "2026-06-22 13:58 KST",
    analyses: [
      {
        id: 101,
        time: "2026-06-22 14:00",
        verdict: "상승",
        summary: "반도체 업황 회복 기대와 외국인 수급이 단기 흐름을 지지합니다.",
        reasons: ["20일 평균 대비 거래량 1.8배 증가", "5일 이동평균선이 20일선을 상향 돌파", "외국인 순매수 흐름 3거래일 연속"],
        risks: ["단기 상승에 따른 차익 실현 가능성", "원/달러 환율 변동성 확대", "메모리 가격 회복 속도 불확실성"]
      },
      {
        id: 102,
        time: "2026-06-22 13:00",
        verdict: "중립",
        summary: "방향성 확인 전까지 주요 지지선 관찰이 필요합니다.",
        reasons: ["단기 이동평균선 부근 횡보", "외국인 수급은 소폭 개선", "거래량은 평균 수준 유지"],
        risks: ["상단 매물대 저항", "환율 민감도", "추가 거래량 확인 필요"]
      }
    ]
  },
  {
    symbol: "000660.KS",
    name: "SK하이닉스",
    price: 189400,
    change: 1.04,
    volumeRatio: "1.4x",
    low20: "184,000",
    high20: "193,500",
    alertStatus: "대기",
    alertDetail: "알림 조건 일부만 충족",
    matchedAlerts: ["업종 강세"],
    dataTime: "2026-06-22 13:57 KST",
    analyses: [
      {
        id: 201,
        time: "2026-06-22 14:00",
        verdict: "상승",
        summary: "HBM 수요 기대가 유지되며 단기 수급도 양호합니다.",
        reasons: ["외국인 순매수 전환", "고점 돌파 시도", "반도체 업종 강세"],
        risks: ["최근 상승폭 부담", "업종 변동성", "실적 기대 선반영"]
      },
      {
        id: 202,
        time: "2026-06-22 13:00",
        verdict: "중립",
        summary: "상승 추세 안에서 단기 숨 고르기가 나타납니다.",
        reasons: ["20일선 상단 유지", "거래량 안정", "업종 흐름 양호"],
        risks: ["고점 매물", "단기 과열", "환율 변화"]
      }
    ]
  },
  {
    symbol: "035420.KS",
    name: "NAVER",
    price: 214500,
    change: -0.46,
    volumeRatio: "0.9x",
    low20: "210,000",
    high20: "222,000",
    alertStatus: "조건 미충족",
    alertDetail: "카카오 알림 없음",
    matchedAlerts: [],
    dataTime: "2026-06-22 13:56 KST",
    analyses: [
      {
        id: 301,
        time: "2026-06-22 14:00",
        verdict: "중립",
        summary: "가격은 지지선 위에 있으나 거래량 확인이 필요합니다.",
        reasons: ["210,000원 지지", "기관 수급 개선", "낙폭 제한"],
        risks: ["거래량 평균 하회", "성장주 변동성", "단기 방향성 부재"]
      },
      {
        id: 302,
        time: "2026-06-22 13:00",
        verdict: "관망",
        summary: "명확한 수급 신호가 없어 관찰이 필요한 구간입니다.",
        reasons: ["지지선 근접", "매도 압력 완화", "업종 보합"],
        risks: ["수급 공백", "저항선 미돌파", "시장 민감도"]
      }
    ]
  },
  {
    symbol: "005380.KS",
    name: "현대차",
    price: 281000,
    change: 0.72,
    volumeRatio: "1.2x",
    low20: "276,000",
    high20: "286,000",
    alertStatus: "대기",
    alertDetail: "장중 조건 재확인 필요",
    matchedAlerts: ["기관 순매수"],
    dataTime: "2026-06-22 13:55 KST",
    analyses: [
      {
        id: 401,
        time: "2026-06-22 14:00",
        verdict: "상승",
        summary: "실적 기대와 안정적인 수급이 완만한 상승을 지지합니다.",
        reasons: ["기관 순매수", "주요 이동평균선 상단", "거래량 점진적 증가"],
        risks: ["환율 변동", "자동차 수요 둔화", "단기 저항선 근접"]
      },
      {
        id: 402,
        time: "2026-06-22 13:00",
        verdict: "중립",
        summary: "추세는 유지되지만 저항선 확인이 필요합니다.",
        reasons: ["지지선 유지", "기관 수급 양호", "낙폭 제한"],
        risks: ["상단 매물", "환율 민감도", "거래량 부족"]
      }
    ]
  }
];

let selectedSymbol = stockData[0].symbol;
let selectedAnalysisId = stockData[0].analyses[0].id;
const currentStock = () => stockData.find((stock) => stock.symbol === selectedSymbol);
const currentAnalysis = () => currentStock().analyses.find((item) => item.id === selectedAnalysisId) || currentStock().analyses[0];

function renderScreen() {
  const stock = currentStock();
  const analysis = currentAnalysis();
  renderWatchlist(stockData, selectedSymbol, selectStock);
  renderAnalysis(stock, analysis);
  renderHistory(stock, selectedAnalysisId, selectAnalysis);
}

function selectStock(symbol) {
  selectedSymbol = symbol;
  selectedAnalysisId = currentStock().analyses[0].id;
  renderScreen();
  showToast(`GET /stocks/${symbol}/analysis/latest 결과를 표시합니다.`);
}

function selectAnalysis(analysisId) {
  selectedAnalysisId = analysisId;
  renderScreen();
  showToast(`GET /stocks/${selectedSymbol}/analysis/${analysisId} 상세를 표시합니다.`);
}

document.querySelector("#app").innerHTML = AppShell(`
  <section class="workspace-grid">
    ${WatchlistPanel()}
    ${AnalysisWorkspace()}
  </section>
`);

document.querySelector("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = document.querySelector("#search-input").value.trim().toLowerCase();
  const match = stockData.find((stock) => stock.name.toLowerCase().includes(query) || stock.symbol.toLowerCase().includes(query));
  if (!query || !match) {
    showToast("현재 mock 관심종목에서 찾지 못했습니다.");
    return;
  }
  selectStock(match.symbol);
  document.querySelector("#search-input").value = "";
});

document.querySelector("#add-symbol-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.querySelector("#add-symbol-input");
  const rawSymbol = input.value.trim().toUpperCase();
  if (!rawSymbol) {
    showToast("추가할 종목 코드를 입력하세요.");
    return;
  }
  const symbol = rawSymbol.includes(".") ? rawSymbol : `${rawSymbol}.KS`;
  if (stockData.some((stock) => stock.symbol === symbol)) {
    showToast("이미 관심종목에 있는 코드입니다.");
    return;
  }
  const id = 500 + stockData.length;
  stockData.push({
    symbol,
    name: "데모 종목",
    price: 100000,
    change: 0,
    volumeRatio: "1.0x",
    low20: "98,000",
    high20: "102,000",
    alertStatus: "조건 미충족",
    alertDetail: "새로 추가된 mock 항목",
    matchedAlerts: [],
    dataTime: "2026-06-22 14:00 KST",
    analyses: [{
      id,
      time: "2026-06-22 14:00",
      verdict: "중립",
      summary: "새로 추가한 데모 종목의 mock 분석입니다.",
      reasons: ["관심종목 추가 동작 확인", "POST /watchlist 예정 흐름", "API 연동 전 UI 상태"],
      risks: ["실제 시세 아님", "AI 분석 아님", "앱 재시작 시 초기화"]
    }]
  });
  input.value = "";
  selectStock(symbol);
});

document.querySelector("#latest-button").addEventListener("click", () => {
  selectedAnalysisId = currentStock().analyses[0].id;
  renderScreen();
  showToast("최신 분석 결과로 돌아왔습니다.");
});

document.querySelector("#run-analysis-button").addEventListener("click", (event) => {
  const runButton = event.currentTarget;
  runButton.disabled = true;
  document.querySelector("#scheduler-status").textContent = "실행 중";
  showToast("POST /scheduler/run?force=true mock 실행 중입니다.");
  window.setTimeout(() => {
    const stock = currentStock();
    stock.dataTime = new Date().toLocaleString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    });
    document.querySelector("#scheduler-status").textContent = "완료";
    runButton.disabled = false;
    renderScreen();
    showToast("스케줄러 실행 결과를 mock 데이터로 반영했습니다.");
  }, 700);
});

renderScreen();
