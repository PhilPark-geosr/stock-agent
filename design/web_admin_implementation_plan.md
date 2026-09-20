# React 웹 기반과 운영자 초대 발급 구현 계약

기준: web_private_beta_design.md의 승인 정책. 이번 범위는 React 공통 기반, 웹 카카오 로그인, 운영자 확인, 초대 발급까지이다. 일반 화면 이전, 코드 등록·사용 확정·베타 권한 부여, 개인 AI 키, Capacitor 실제 패키징과 배포는 후속 작업이다.

## 구조와 인터페이스

- web/에 React·TypeScript·Vite·React Router 프로젝트를 만들고 npm 잠금 파일을 사용한다. Electron 전용 window.desktop에 의존하지 않는다.
- 개발은 Vite 프록시, 운영은 FastAPI가 빌드된 웹 파일을 제공하는 동일 출처 구성이다. /login, /admin 새로고침을 지원하되 기존 API·콜백을 SPA로 덮어쓰지 않는다.
- 기존 로그인 시도 생성·카카오 콜백·서비스 세션을 재사용한다. 웹 교환 POST /auth/web/login-attempts/{id}/exchange는 HttpOnly·SameSite=Lax·Path=/ 쿠키를 설정한다. 토큰을 JSON·브라우저 영구 저장소에 노출하지 않는다.
- GET /auth/web/session은 본인 ID와 운영자 여부, DELETE는 세션 폐기와 쿠키 삭제를 제공한다. 쿠키는 기본 Secure이며 로컬 개발만 WEB_COOKIE_SECURE=false로 해제한다. 기존 30일 세션을 재사용한다.
- 변경 요청은 WEB_ORIGIN과 Origin을 검사하며 없거나 다르면 거부한다. ADMIN_ACCOUNT_ID 하나와 서버가 인증한 계정 ID를 비교한다. 설정 누락 시 운영자는 없다.
- GET /admin은 미로그인 시 /login, 비운영자는 403, 운영자는 React 화면으로 연결한다. POST /admin/invitations는 201 {code, expires_at}, 미로그인 401, 비운영자 403이다.
- 로그인 화면에서 본인 계정 ID를 확인한 뒤 서버 설정으로 운영자를 지정한다. 먼저 로그인한 계정을 자동 승격하지 않는다.
- 발급기는 코드 생성·UTC 시점과 7일 기한 결정·초대 생성·저장 요청·결과 반환을 조율한다. 별도 생성기·정책 객체는 두지 않는다.
- secrets.token_urlsafe(32)로 코드를 만들고 DB에는 SHA-256 해시, 식별자, 발급·만료·사용 시각을 저장한다. 해시는 유일하며 원문은 성공 응답으로만 제공한다. 조회는 입력 코드의 해시로 수행한다.
- UI는 발급·복사·한국 시간 기한·로그아웃만 제공한다. 요청 중 중복 클릭을 막고 자동 재시도하지 않는다. 실패를 성공으로 표시하지 않는다.
- 운영자 발급은 베타 권한과 독립적이다. 일반 서비스의 베타 접근 통제를 구현 완료로 간주하지 않는다.

## TDD와 커밋

각 단계는 실패 테스트 확인 → 최소 구현 → 리팩터링 → 관련 테스트 통과 순서로 진행하며 통과 상태로 커밋한다.

1. docs: finalize web stack and invitation implementation plan
2. feat: implement invitation issuance domain and service
3. feat: persist issued invitations
4. feat: add browser sessions and operator invitation api
5. feat: establish React web foundation and login
6. feat: add admin invitation page and browser verification

## 검증 계약

| 영역 | 기대 동작 |
| --- | --- |
| 발급·기한 | 요청당 미사용 1개, 정확한 7일 기한, 직전 가능·경계 이후 불가·사용된 초대 불가 |
| 저장 | 연결을 새로 열어도 조회, 미발급 없음, 원문 미저장, 해시 중복 거부, 저장 실패 성공 반환 금지 |
| 마이그레이션 | 빈 DB·기존 DB 업그레이드, 기존 계정·분석·알림 기록 보존 |
| 인증 | 실제 테스트 세션을 통한 만료·폐기·미로그인 401, 비운영자 403, 거부 요청 저장 0건 |
| 운영자 | 지정 계정만 허용, 첫 로그인 자동 승격 없음, 미지정 접근 거부, 베타 권한 없이 발급 |
| 웹 세션 | 대기·성공·만료·잘못된 verifier·재사용, 쿠키 속성·토큰 미노출·출처 검사·로그아웃 |
| UI | 로그인·접근 거부·코드와 기한 표시·복사·중복 클릭 억제·세션 만료·오류 표시 |
| 통합 | 빌드된 React+FastAPI에서 직접 접속·새로고침·로그인 복귀·발급 DB 기록·로그아웃 |

pytest, Vitest·React Testing Library, Playwright를 사용한다. 외부 카카오·AI 호출은 대역으로 처리하고 제품 API에 테스트용 로그인 우회를 추가하지 않는다. 전체 Python·기존 Electron 테스트, 새 웹 타입 검사·빌드·브라우저 테스트로 마무리한다.

기존 변경과 00b8884 커밋을 보존한다. desktop-demo/pnpm-lock.yaml은 건드리지 않는다. 자동 푸시·배포는 하지 않는다.
