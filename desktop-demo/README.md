# Stock Agent Electron Client

Stock Agent FastAPI 백엔드에 연결해 관심종목, 분석 결과, 스케줄러와 사용자 알림 조건을 관리하는 Electron 클라이언트입니다.

## Electron을 사용한 이유

- 기존 FastAPI 백엔드를 유지하면서 데스크톱 화면을 제공할 수 있습니다.
- HTML, CSS, JavaScript로 화면을 만들기 때문에 현재 웹 대시보드 구조와 지식을 재사용하기 쉽습니다.
- 나중에 로컬 실행 앱으로 포장할 때 Windows/macOS/Linux 배포 흐름을 비교적 단순하게 가져갈 수 있습니다.
- main process와 renderer process를 분리하면 API 키나 카카오 토큰 같은 민감 정보는 백엔드에 남기고, 화면은 안전한 preload 경계 안에서 다룰 수 있습니다.

## 요구사항

- Node.js 22.12 이상
- npm 10 이상
- Python 3.11 가상환경 (`../.venv` 권장)
- 루트 프로젝트 의존성 설치 (`python -m pip install -e .`)

## 실행

```powershell
cd desktop-demo
npm install
npm start
```

Electron은 `http://127.0.0.1:8000/health`를 확인하고 백엔드가 실행 중이 아니면 루트 가상환경으로 uvicorn을 자동 실행합니다. 이미 실행 중인 백엔드가 있으면 해당 프로세스를 그대로 사용합니다. 다른 주소는 `STOCK_AGENT_API_URL` 환경 변수로 지정할 수 있습니다.

Electron 42.4.1을 사용합니다. Node.js 18 환경에서는 설치되지 않으므로 Node.js를 먼저 업그레이드해야 합니다.

## 컴포넌트 구조

화면 전체를 한 파일에서 수정하지 않도록 레이아웃과 기능 영역을 분리했습니다. React를 추가한 구조는 아니며, 현재 데모의 순수 JavaScript 방식을 유지한 작은 UI 모듈입니다.

```text
src/
  components/
    layout.js       # 앱 shell, 사이드바, 상단 검색/실행 영역
    toast.js        # 공통 사용자 알림
  features/
    watchlist.js    # 관심종목 마크업과 목록 렌더링
    analysis.js     # 최신 분석, 근거/위험, 지표, 분석 이력
    alerts.js       # 사용자 알림 조건과 카카오 로그인
  index.html        # 앱 마운트 지점
  renderer.js       # API 응답 상태와 컴포넌트 이벤트 연결
  styles.css        # 공통 화면 스타일
```

기능을 확장할 때는 해당 `features` 모듈에 UI와 렌더링 함수를 추가하고, `renderer.js`에서는 상태와 이벤트만 연결합니다. 여러 기능에서 함께 쓰는 UI는 `components`에 둡니다.

## 포함된 동작

- 사이드바에서 관심종목, 최신 분석, 이력, 알림 독립 화면 전환
- 관심종목 선택 및 검색
- 관심종목 추가 및 삭제
- 최신/과거 분석 전환
- 수동 스케줄러 실행
- 사용자 정의 알림 조건 검증, 저장 및 삭제
- 카카오 OAuth 로그인 열기
- 백엔드 연결 상태와 API 오류 안내

## 연동 구조

renderer는 FastAPI를 직접 호출하지 않습니다. `preload.js`가 허용한 메서드를 호출하면 main process가 로컬 HTTP 요청을 수행합니다. Gemini와 카카오 키 등 민감 정보는 루트 `.env`와 FastAPI 백엔드에서만 관리합니다.
