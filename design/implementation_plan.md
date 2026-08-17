# TDD 기반 로그인·다중 사용자 구현 계획

## 목표와 실행 원칙

카카오 로그인으로 식별된 사용자가 자신의 관심 종목 구독과 알림 조건만 다루도록 기존 단일 사용자 서비스를 전환한다. 종목 분석은 사용자별로 복제하지 않고 안전한 공유 분석으로 유지한다.

구현은 `Red → Green → Refactor`의 TDD 순서를 따른다.

1. 원하는 동작을 나타내는 테스트를 먼저 작성한다.
2. 테스트가 기대한 이유로 실패하는지 확인한다.
3. 테스트를 통과하는 최소 구현을 추가한다.
4. 관련 테스트가 통과하는 상태에서 책임과 중복을 정리한다.
5. 관련 테스트와 상위 회귀 테스트를 통과시킨 뒤 의미 있는 단위로 커밋한다.

실패하는 테스트만 별도 커밋하지 않는다. 인증, 구독 소유권, Electron UI처럼 책임이 다른 변경을 한 커밋에 섞지 않는다. 외부 카카오와 네트워크 호출은 자동 테스트에서 대역으로 검증한다.

## 구현 에이전트 운영

공유 작업 트리의 충돌을 피하기 위해 구현 에이전트를 한 번에 하나씩 순차 배정한다.

| 역할 | 책임 |
| --- | --- |
| 메인 에이전트 | 설계 관리, 작업 배정, 코드 리뷰, 통합 검증 |
| 인증 구현 에이전트 | 사용자 계정, 로그인 시도, 서비스 세션, 카카오 로그인 어댑터 |
| 소유권 구현 에이전트 | 관심 종목 구독, 알림 조건, 분석 접근 제어, DB 마이그레이션 |
| Electron 구현 에이전트 | 로그인 UI, IPC, 안전한 세션 저장, 화면 전환 |

각 에이전트는 커밋 해시, 변경 요약과 실행한 테스트를 메인 에이전트에 보고한다. 기존 책임이나 확정된 도메인 모델을 바꿔야 한다면 구현과 커밋을 중단하고 설계 논의를 요청한다.

## 1단계: 설계 기준선 확정

`CONTEXT.md`와 로그인 설계문서에 다음 결정을 기록한다.

- `WatchlistSubscription` 하나는 한 `UserAccount`와 한 `StockSymbol` 사이의 관계다.
- 구독은 독립적인 식별자와 시작·종료 생명주기를 가진 애그리게이트 루트다.
- `UserAccount`는 구독 식별자나 구독 컬렉션을 저장하지 않는다.
- 사용자별 구독 목록은 저장소가 `ownerId`로 조회한다.
- `StockSymbol`은 별도 `Stock` 엔티티가 아닌 값 객체다.
- 구독 종료 시 활성 알림 조건도 함께 종료하며, 재구독은 새로운 구독 식별자를 만든다.

검증:

```text
git diff --check
Mermaid 클래스 관계와 다중성 수동 확인
```

커밋: `docs: define watchlist subscription and TDD implementation plan`

## 2단계: Alembic 마이그레이션 토대

담당: 소유권 구현 에이전트

Red:

- 빈 SQLite DB가 최신 스키마로 생성된다.
- 현재 레거시 스키마가 데이터 손실 없이 기준 리비전으로 등록된다.
- 예상하지 못한 스키마는 자동으로 stamp하지 않는다.

Green:

- Alembic 의존성과 설정을 추가한다.
- 현재 스키마를 나타내는 기준 리비전을 만든다.
- 기존 DB는 예상 테이블·컬럼을 검증한 후 기준 리비전으로 등록한다.
- 기존 `init_db()`의 수동 스키마 변경 책임을 마이그레이션으로 옮긴다.
- 로컬 Electron 백엔드 시작 전에 마이그레이션을 실행한다.

검증: `uv run pytest tests/test_migrations.py tests/test_settings.py tests/test_api.py`

커밋: `chore: introduce versioned database migrations`

## 3단계: 사용자 계정과 로그인 서비스

담당: 인증 구현 에이전트

Red:

- 유효한 `LoginIdentity`로 신규 계정을 생성한다.
- 기존 신원으로 로그인하면 같은 계정을 반환한다.
- 같은 제공자와 외부 사용자 식별자가 여러 계정에 속할 수 없다.
- 동시 최초 로그인에도 계정이 하나만 생성된다.
- 로그인 신원 없이 계정을 생성할 수 없다.

Green:

- `UserAccount`, `LoginIdentity`, `ExternalLoginCredential`을 추가한다.
- `ExternalLogin`, `UserAccountRepository` 인터페이스를 정의한다.
- `LoginService.login(credential)`이 신원을 받아 기존 계정을 찾거나 새 계정을 등록한다.
- DB 복합 유일성 제약과 `save_or_get_existing`으로 동시 생성을 방지한다.

```python
class LoginService:
    def login(self, credential: ExternalLoginCredential) -> UserAccount:
        identity = self.external_login.login(credential)
        existing = self.accounts.find_by_login_identity(identity)
        if existing:
            return existing
        return self.accounts.save_or_get_existing(
            UserAccount.register(identity)
        )
```

검증: `uv run pytest tests/test_login_domain.py tests/test_user_account_repository.py`

커밋: `feat: add user account login domain`

## 4단계: 로그인 시도와 서비스 세션

담당: 인증 구현 에이전트

Red:

- 로그인 시도는 생성 후 5분에 만료된다.
- 잘못된 `state`와 verifier를 거부한다.
- 완료 전 교환은 pending이고, 완료된 시도는 한 번만 교환된다.
- 유효·만료·폐기 세션을 구분하고 로그아웃 시 현재 세션을 폐기한다.

Green:

- 인증 지원 모델 `LoginAttempt`, `AuthSession`을 추가한다.
- `LoginAttemptService`, `SessionService`와 저장소를 추가한다.
- 32바이트 이상의 난수 세션 토큰을 발급하고 서버에는 SHA-256 해시만 저장한다.
- 서비스 세션은 발급 후 30일에 절대 만료된다.
- 로그인 시도 생성·교환, 세션 조회·삭제 API를 제공한다.

검증: `uv run pytest tests/test_login_attempt.py tests/test_auth_session.py tests/test_auth_api.py`

커밋: `feat: add login attempts and service sessions`

## 5단계: 카카오 서비스 로그인

담당: 인증 구현 에이전트

Red:

- 인가 URL에 고유 `state`와 정확한 redirect URI를 포함한다.
- 인가 코드 교환과 `/v2/user/me` 응답을 카카오 `LoginIdentity`로 변환한다.
- 실패·취소·만료 콜백을 처리한다.
- 추가 권한을 요청하지 않고 카카오 토큰을 저장하거나 응답에 노출하지 않는다.

Green:

- `KakaoExternalLogin`과 카카오 콜백 API를 추가한다.
- 카카오 회원번호만 `LoginIdentity("kakao", id)`에 사용한다.
- access/refresh token은 신원 확인 직후 폐기한다.
- 기존 전역 `.env` 토큰 기반 로그인 흐름을 제거하거나 비활성화한다.

검증: `uv run pytest tests/test_kakao_external_login.py tests/test_auth_api.py`

커밋: `feat: integrate Kakao service login`

## 6단계: 사용자별 관심 종목 구독

담당: 소유권 구현 에이전트

Red:

- 같은 사용자의 같은 종목 중복 요청은 기존 활성 구독을 반환한다.
- 서로 다른 사용자는 같은 종목을 독립적으로 구독할 수 있다.
- 사용자별 목록과 종료 권한이 격리된다.
- 종료 후 재구독은 새로운 구독 식별자를 만든다.
- 스케줄러 종목 목록은 활성 구독에서 종목 코드를 중복 제거한다.
- 소유자 없는 레거시 구독은 사용자 API와 스케줄러에 노출되지 않는다.

Green:

- 기존 `WatchlistItem` 개념을 `WatchlistSubscription`으로 정렬한다.
- 기존 테이블에는 `user_account_id`, `ended_at`을 추가하고 `created_at`을 `started_at`으로 해석한다.
- 활성 `(user_account_id, symbol)` 조합의 유일성을 DB에서 보장한다.
- 기존 행은 소유자 없이 보존한다.
- 모든 관심 종목 API는 인증된 현재 계정으로 범위를 제한한다.

```python
@dataclass
class WatchlistSubscription:
    id: SubscriptionId
    owner_id: UserAccountId
    symbol: StockSymbol
    started_at: datetime
    ended_at: datetime | None = None

    def end(self, ended_at: datetime) -> None:
        if self.ended_at is None:
            self.ended_at = ended_at
```

`UserAccount`에는 `subscription_ids`나 `subscriptions` 필드를 추가하지 않는다.

```python
class WatchlistSubscriptionRepository(Protocol):
    def find_active(self, owner_id, symbol): ...
    def list_active_by_owner(self, owner_id): ...
    def list_distinct_active_symbols(self): ...
    def save_or_get_existing(self, subscription): ...
```

API는 현재 경로를 유지한다.

- `GET /watchlist`: 현재 사용자의 활성 구독 조회
- `POST /watchlist`: 생성하거나 기존 활성 구독 반환
- `DELETE /watchlist/{symbol}`: 현재 사용자의 활성 구독 논리 종료

검증: `uv run pytest tests/test_watchlist_subscription.py tests/test_watchlist_repository.py tests/test_scheduler.py` 및 `uv run pytest tests/test_api.py -k watchlist`

커밋: `feat: scope watchlist subscriptions by account`

## 7단계: 사용자별 알림 조건 소유권

담당: 소유권 구현 에이전트

Red:

- 조건 생성에는 현재 사용자의 활성 구독이 필요하다.
- 조건은 구독 식별자를 통해 소유자와 종목을 결정한다.
- 다른 사용자의 조건을 조회하거나 종료할 수 없다.
- 구독 종료 시 활성 조건도 종료되고 재구독 시 복원되지 않는다.
- 소유자 없는 레거시 조건은 노출되지 않는다.

Green:

- 조건에 `watchlist_subscription_id`, `ended_at`을 추가한다.
- 현재 계정의 활성 구독을 기준으로 조건 API를 제한한다.
- 실제 삭제 대신 종료하고, 구독 종료와 조건 종료를 한 트랜잭션으로 처리한다.

검증: `uv run pytest tests/test_alert_condition_ownership.py` 및 `uv run pytest tests/test_api.py -k alert_condition`

커밋: `feat: scope alert conditions to subscriptions`

## 8단계: 공유 분석 경계 보호

담당: 소유권 구현 에이전트

Red:

- 사용자 조건이 공유 분석 프롬프트에 전달되지 않는다.
- 동일 종목 분석은 사용자별 복사본 없이 공유된다.
- 활성 구독이 있는 사용자만 공유 분석을 조회할 수 있다.
- 사용자별 알림 발송이 호출되지 않는다.
- 안전성을 확인할 수 없는 기존 분석은 새 사용자에게 노출되지 않는다.

Green:

- 공유 분석에는 시스템 시장 조건만 전달한다.
- 분석 서비스에서 사용자 조건 저장소 의존을 제거한다.
- 기존 분석은 `shared_safe=false`, 전환 이후 시스템 조건 전용 분석은 `shared_safe=true`로 구분한다.
- 사용자 알림 조건 CRUD는 유지하되 평가·발송은 다음 설계까지 중단한다.
- 기존 전역 카카오 알림 실행 경로를 비활성화한다.

검증: `uv run pytest tests/test_analysis_graph.py tests/test_scheduler.py`, `uv run pytest tests/test_api.py -k analysis`, `uv run pytest`

커밋: `refactor: isolate shared analysis from user alert rules`

## 9단계: Electron 로그인 UI와 세션 복원

담당: Electron 구현 에이전트

재사용 가능한 `AppRoot`, `LoginPage`, `OAuthLoginButton`, `KakaoLoginButton`, `AccountMenu`, `AuthController`, `AuthGateway`를 구성한다. 기존 Electron 데모의 녹색 배경, 흰색 카드, 라임 포인트와 타이포그래피를 유지한다.

Red:

- 세션 유무에 따라 로그인 화면 또는 분석 화면을 표시한다.
- 로그인 중 중복 요청을 막고 성공 후 분석 화면을 한 번만 초기화한다.
- 실패·취소·만료 시 재시도할 수 있다.
- 401 수신과 로그아웃 시 로그인 화면으로 전환한다.
- renderer와 `localStorage`에 세션 토큰이 노출되지 않는다.

Green:

- main process가 verifier 생성, 기본 브라우저 열기와 로그인 완료 확인을 담당한다.
- 세션 토큰은 main process에서만 유지하고 `safeStorage`로 암호화해 저장한다.
- 암호화가 불가능하면 평문으로 저장하지 않고 현재 프로세스 메모리에만 유지한다.
- preload IPC를 통해 renderer에 인증 동작만 노출한다.
- 백엔드 요청에 bearer token을 추가하고 401이면 저장 토큰을 제거한다.
- 기존 알림 연결 UI를 비활성화하고 조건 평가 중단 상태를 안내한다.

검증: `npm run check`, `npm test`, `uv run pytest`

커밋: `feat: add Electron Kakao login gate`

## 10단계: 통합 검증과 운영 문서

담당: 메인 에이전트

수동 시나리오:

1. 사용자 A의 최초 로그인에서 계정을 생성한다.
2. 앱 재실행 시 암호화된 유효 세션을 복원한다.
3. A와 B가 같은 종목을 독립적으로 구독한다.
4. 서로의 구독과 알림 조건이 노출되지 않는다.
5. 해당 종목의 공유 분석은 한 번만 생성한다.
6. A의 구독 종료가 B의 구독이나 공유 분석에 영향을 주지 않는다.
7. A가 재구독하면 새 구독 식별자를 받고 과거 조건은 복원되지 않는다.
8. 로그아웃하면 서버와 로컬 세션을 제거하고 로그인 화면을 표시한다.

전체 검증:

```text
uv run pytest
npm run check
npm test
git diff --check
git status --short
```

카카오 개발자 콘솔, redirect URI, 필수 환경변수, Alembic 실행 및 로컬 Electron 로그인 방법을 문서화한다. 사용자별 알림 평가·발송이 아직 비활성 상태임을 명시한다.

커밋: `docs: document multi-user login setup`

## 하드스톱 조건

다음 상황에서는 구현과 커밋을 중단하고 설계를 다시 논의한다.

- `UserAccount`에 구독 컬렉션을 포함해야 한다.
- `WatchlistSubscription` 애그리게이트 경계를 바꿔야 한다.
- 별도 `Stock` 엔티티나 종목 마스터가 필요하다.
- 사용자별 `AlertEvaluation` 또는 `NotificationConnection`을 구현해야 한다.
- 카카오 이메일·프로필·`talk_message` 등 추가 권한이 필요하다.
- 인증 API 또는 30일 세션 정책을 바꿔야 한다.
- 기존 미귀속 데이터를 특정 사용자에게 자동 귀속해야 한다.
- 마이그레이션에서 기존 데이터를 삭제해야 한다.
- 공유 분석에 사용자 조건을 다시 포함해야 한다.
