# Stock Agent Electron Demo

FastAPI나 외부 API에 연결하지 않고 Stock Agent의 데스크톱 UI와 사용자 흐름을 확인하는 Electron 데모입니다.

## Electron을 사용한 이유

- 기존 FastAPI 백엔드와 분리해서 데스크톱 화면만 빠르게 검증할 수 있습니다.
- HTML, CSS, JavaScript로 화면을 만들기 때문에 현재 웹 대시보드 구조와 지식을 재사용하기 쉽습니다.
- 나중에 로컬 실행 앱으로 포장할 때 Windows/macOS/Linux 배포 흐름을 비교적 단순하게 가져갈 수 있습니다.
- main process와 renderer process를 분리하면 API 키나 카카오 토큰 같은 민감 정보는 백엔드에 남기고, 화면은 안전한 preload 경계 안에서 다룰 수 있습니다.

## 요구사항

- Node.js 22.12 이상
- npm 10 이상

## 실행

```powershell
cd desktop-demo
npm install
npm start
```

Electron 42.4.1을 사용합니다. 저장소의 기존 Node.js 18 환경에서는 설치되지 않으므로 Node.js를 먼저 업그레이드해야 합니다.

## 정적 화면 확인

`src/index.html`은 브라우저로 직접 열어도 핵심 화면과 mock 상호작용을 확인할 수 있습니다.

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
  index.html        # 앱 마운트 지점
  renderer.js       # mock 데이터, 화면 상태, 컴포넌트 이벤트 연결
  styles.css        # 공통 화면 스타일
```

기능을 확장할 때는 해당 `features` 모듈에 UI와 렌더링 함수를 추가하고, `renderer.js`에서는 상태와 이벤트만 연결합니다. 여러 기능에서 함께 쓰는 UI는 `components`에 둡니다.

## 포함된 동작

- 관심종목 선택 및 검색
- 데모 종목 추가
- 최신/과거 분석 전환
- mock 갱신 시각 변경
- 검색, 선택, 추가, 실행 결과 안내 토스트

## 실제 연동에서 교체할 부분

`src/renderer.js`의 `stockData`와 상태 변경 함수를 FastAPI 호출로 교체합니다. Electron의 main process에는 API 키를 두지 않고, 인증 및 민감 정보는 백엔드가 관리하도록 유지합니다.
