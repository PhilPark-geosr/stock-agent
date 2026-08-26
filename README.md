# Stock Agent

카카오 서비스 로그인과 사용자별 관심 종목 구독을 제공하는 Electron 기반 주식 분석 앱입니다. FastAPI 백엔드는 `yfinance` 시장 데이터와 Gemini를 이용해 종목별 공유 분석을 생성하고 SQLite에 보관합니다.

## 요구사항

- Python 3.11 이상과 [uv](https://docs.astral.sh/uv/)
- Node.js 22.12 이상과 npm 10 이상
- Gemini API 키
- 카카오 Developers 애플리케이션의 REST API 키

## 카카오 Developers 설정

카카오 Developers에서 애플리케이션을 선택한 뒤 다음을 설정합니다.

1. **카카오 로그인**을 활성화합니다.
2. REST API 키의 **카카오 로그인 Redirect URI**에 로그인과 알림 연결용 주소를 모두 정확히 등록합니다.

   ```text
   http://127.0.0.1:8000/auth/kakao/callback
   http://127.0.0.1:8000/notification-connections/kakao/callback
   ```

3. REST API 키를 복사합니다.
4. 클라이언트 시크릿을 활성화한 경우에만 해당 값을 함께 복사합니다.

서비스 로그인은 카카오 회원번호만 확인하고 `talk_message`를 요청하지 않습니다. 로그인 뒤 사용자가 별도로 **카카오 알림 연결**을 선택할 때만 `talk_message` 추가 동의를 요청합니다. `localhost`와 `127.0.0.1`, 포트, 경로 및 마지막 슬래시는 서로 다른 Redirect URI로 취급되므로 `.env`와 카카오 콘솔의 값을 완전히 일치시켜야 합니다.

## 설치 및 환경변수

```powershell
uv sync
Copy-Item .env.example .env
```

`.env`에서 다음 값을 설정합니다.

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=sqlite:///./stock_agent.db

KAKAO_REST_API_KEY=your-kakao-rest-api-key
KAKAO_REDIRECT_URI=http://127.0.0.1:8000/auth/kakao/callback
KAKAO_NOTIFICATION_REDIRECT_URI=http://127.0.0.1:8000/notification-connections/kakao/callback
KAKAO_CLIENT_SECRET=
NOTIFICATION_TOKEN_FERNET_KEY=generated-fernet-key
```

- `KAKAO_REST_API_KEY`는 필수입니다.
- `KAKAO_CLIENT_SECRET`은 카카오 콘솔에서 시크릿을 활성화했을 때만 입력합니다.
- `KAKAO_NOTIFICATION_REDIRECT_URI`는 카카오 콘솔에 별도로 등록한 알림 연결 callback과 정확히 같아야 합니다.
- `NOTIFICATION_TOKEN_FERNET_KEY`는 카카오 알림 access/refresh token 암호화에 필수입니다. 누락되면 로그인과 분석은 계속 동작하지만 알림 연결 API만 503을 반환합니다.
- `KAKAO_ACCESS_TOKEN`, `KAKAO_REFRESH_TOKEN`은 서비스 로그인 설정이 아닙니다. 로그인 과정에서 받은 카카오 토큰은 회원번호 확인 후 저장하지 않습니다.
- 서버 시작 시 Alembic 마이그레이션이 자동으로 최신 리비전까지 적용됩니다.

Fernet 키는 한 번 생성해 안전하게 보관하고, 이미 저장된 토큰이 있는 상태에서 임의로 교체하지 않습니다.

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 실행

### Electron 앱

```powershell
Set-Location desktop-demo
npm ci
npm start
```

기본 설정에서는 Electron이 `http://127.0.0.1:8000/health`를 확인합니다. 서버가 없으면 프로젝트 루트의 `.venv` 또는 `.python311`을 이용해 FastAPI를 자동 실행합니다. 백엔드를 직접 실행하려면 다음 명령을 먼저 실행해도 됩니다.

```powershell
uv run uvicorn app.main:app --reload
```

별도 중앙 서버를 사용할 때는 Electron을 시작하기 전에 `STOCK_AGENT_API_URL`을 설정합니다.

```powershell
$env:STOCK_AGENT_API_URL = "https://stock-agent.example.com"
npm start
```

## 로그인 흐름과 세션

1. 앱 시작 시 Electron main process가 저장된 서비스 세션을 복원합니다.
2. 유효한 세션이 없으면 로그인 화면을 표시합니다.
3. **카카오로 로그인**을 누르면 앱이 5분짜리 로그인 시도를 만들고 기본 브라우저에서 카카오 로그인을 엽니다.
4. 카카오가 FastAPI 콜백으로 인가 코드를 전달하면 서버가 `/v2/user/me`의 회원번호를 `LoginIdentity`로 변환해 계정을 조회하거나 생성합니다.
5. Electron은 완료된 로그인 시도를 한 번만 교환해 Stock Agent 자체 세션을 받고 분석 화면으로 전환합니다.

서비스 세션은 30일 절대 만료이며, 서버에는 원문이 아니라 SHA-256 해시만 저장됩니다. 원문 세션 토큰은 renderer나 `localStorage`에 노출하지 않고 Electron main process에서만 사용합니다. 저장 시 OS 암호화 기능인 Electron `safeStorage`를 사용하며, 암호화를 사용할 수 없는 환경에서는 디스크에 평문으로 기록하지 않고 현재 실행의 메모리에만 유지합니다. 401 응답이나 로그아웃 시 로컬 토큰을 제거합니다.

## 현재 1차 구현 범위

- 관심 종목 구독과 자연어 알림 조건은 로그인한 사용자 계정별로 격리됩니다.
- 같은 종목의 분석은 사용자별로 복제하지 않고 공용으로 생성합니다.
- 사용자는 자신이 활성 구독한 종목의 안전한 공유 분석만 조회하거나 수동 실행할 수 있습니다.
- 공유 분석에는 시스템 시장 조건만 사용하며 사용자 알림 조건은 저장·조회·종료까지만 제공합니다.
- 스케줄 분석에서 시스템 신호가 발생하면 활성 구독자 중 카카오 알림을 연결한 사용자에게 기본 알림 한 건을 발송하고 사용자별 성공·실패 이력을 기록합니다.
- 사용자별 조건 평가는 후속 설계 범위입니다.

서비스 로그인 자체에는 `talk_message` 권한이나 메시지 토큰이 필요하지 않으며, 알림 연결은 로그인과 별도의 동의·생명주기를 가집니다.

## 주요 API

인증 API를 제외한 사용자 데이터 및 분석 API는 `Authorization: Bearer <service-session-token>`을 요구합니다.

- `POST /auth/login-attempts` — 브라우저 로그인 시도 생성
- `POST /auth/login-attempts/{attempt_id}/exchange` — 완료된 로그인 시도를 서비스 세션으로 교환
- `GET /auth/session`, `DELETE /auth/session` — 현재 세션 확인 및 로그아웃
- `GET /auth/kakao/callback` — 카카오 인가 콜백
- `POST /notification-connections/kakao/authorize` — 카카오 알림 추가 동의 시작
- `GET`, `DELETE /notification-connections/kakao` — 현재 사용자의 알림 연결 조회·해제
- `GET /notification-connections/kakao/callback` — 카카오 알림 연결 콜백
- `GET`, `POST`, `DELETE /watchlist` — 현재 사용자 관심 종목 구독 관리
- `GET`, `POST`, `DELETE /alert-conditions` — 현재 사용자 알림 조건 관리
- `GET /stocks/{symbol}/analysis`, `GET /stocks/{symbol}/analysis/latest` — 구독 종목의 공유 분석 조회
- `POST /stocks/{symbol}/analysis` — 구독 종목의 공유 분석 수동 실행

## 테스트

```powershell
uv run pytest
Set-Location desktop-demo
npm run check
npm test
```

카카오 HTTP 요청은 자동 테스트에서 대역으로 검증합니다. 실제 카카오 로그인 스모크 테스트에는 카카오 Developers 설정과 유효한 키가 필요합니다.
