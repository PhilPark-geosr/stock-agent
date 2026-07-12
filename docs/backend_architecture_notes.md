# 백엔드 아키텍처 정리 노트

이 문서는 issue #12 / PR #13에서 정리한 백엔드 패키지 구조와 레이어드 아키텍처 결정을 기록한다. 다음 구조 설계와 후속 리팩토링에서 기준 문서로 사용한다.

## 현재 구조 요약

이번 리팩토링의 목표는 단순한 파일 이동이 아니라, 레이어 경계와 의존 방향을 코드에서 드러내는 것이었다.

현재 백엔드는 다음 구조를 기준으로 한다.

```text
app/
  api/             HTTP route와 FastAPI dependency wiring
  core/            설정, DB 세션, composition root, scheduler runtime
  domain/          핵심 도메인 개념과 도메인 helper
  schemas/         Pydantic/API 데이터 계약
  interfaces/      Application Layer가 의존하는 Protocol 계약
  services/        애플리케이션 유스케이스
  application/     분석 workflow orchestration
  repositories/    SQLAlchemy repository 구현체
  integrations/    yfinance/Kakao/Gemini 외부 adapter
  tools/           LangChain tool 구현체
  templates/       Jinja HTML 템플릿
```

핵심 의존 방향은 다음과 같다.

```text
api/routes
  -> services
    -> interfaces

core/container
  -> services + concrete implementations

application / repositories / integrations
  -> implement interfaces
```

`services`는 concrete infrastructure class를 직접 import하지 않는다. 대신 `app.interfaces`의 Protocol을 의존한다. 실제 구현체 조립은 `app/core/container.py`와 `app/api/deps.py`가 담당한다.

## 레이어드 아키텍처

```text
┌──────────────────────────────────────────────────────────────┐
│ Presentation Layer                                           │
│ app/api, app/templates                                       │
│ HTTP 요청/응답, FastAPI dependency, HTML template             │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Application Layer                                            │
│ app/services                                                 │
│ 분석 실행, 저장 흐름, 알림 판단, 스케줄 배치 유스케이스        │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Domain / Interface Layer                                     │
│ app/domain, app/schemas, app/interfaces                      │
│ 도메인 개념, API 데이터 계약, 외부 구현체에 대한 추상 계약      │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Infrastructure / Adapter Layer                               │
│ app/repositories, app/integrations, app/tools                 │
│ DB, LLM, yfinance, Kakao, LangChain tool 구현체                │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Composition / Runtime                                        │
│ app/core/container.py, app/core/scheduler_runtime.py          │
│ concrete 구현체 조립과 백그라운드 runtime wiring               │
└──────────────────────────────────────────────────────────────┘
```

이 구조는 순수한 DDD나 완전한 헥사고날 아키텍처라기보다, FastAPI 프로젝트에 맞춘 실용적인 레이어드 아키텍처에 의존성 역전 원칙을 적용한 형태다.

## 패키지별 책임

| 패키지 | 책임 | 경계 |
| --- | --- | --- |
| `app.api` | HTTP endpoint와 FastAPI dependency | route는 유스케이스 실행을 service에 위임한다. |
| `app.core` | 설정, DB 세션, runtime, composition root | concrete 구현체 조립은 여기에서 한다. |
| `app.domain` | 도메인 개념 | 알림 조건, ORM 모델, symbol 정규화 helper를 둔다. |
| `app.schemas` | Pydantic 데이터 계약 | API 요청/응답과 agent 입출력 데이터 구조를 둔다. |
| `app.interfaces` | Protocol 계약 | service가 의존하는 repository, provider, agent, notifier 인터페이스를 둔다. |
| `app.services` | Application use case | concrete repository, yfinance, Kakao, Gemini, FastAPI를 직접 알지 않는다. |
| `app.application` | Application workflow | 분석 graph와 custom rule context 수집 흐름을 둔다. |
| `app.repositories` | DB adapter | `app.interfaces.repositories`의 SQLAlchemy 구현체를 둔다. |
| `app.integrations` | 외부 API adapter | yfinance, Kakao, Gemini 같은 외부 연동 세부사항을 둔다. |
| `app.tools` | Agent tool adapter | custom rule agent가 사용하는 LangChain tool을 둔다. |

## 의존성 역전 적용 내용

이번 PR에서 `AnalysisService`는 다음 concrete 구현체를 직접 알지 않게 되었다.

- `AnalysisRepository`, `WatchlistRepository`, `AlertConditionRepository`
- `YFinanceMarketDataProvider`
- `GeminiAnalysisAgent`, `MainAnalysisAgent`
- `KakaoAlertNotifier`
- FastAPI `Depends`
- SQLAlchemy `Session`

대신 다음 인터페이스를 의존한다.

- `AnalysisRepository`, `WatchlistRepository`, `AlertConditionRepository` Protocol
- `MarketDataProvider`
- `AnalysisAgent`
- `AlertNotifier`

구현체 클래스는 자신이 따르는 Protocol을 명시적으로 상속한다.

```python
class GeminiAnalysisAgent(AnalysisAgent):
    ...

class YFinanceMarketDataProvider(MarketDataProvider):
    ...

class KakaoAlertNotifier(AlertNotifier):
    ...
```

## 현재 건강도 평가

현재 구조는 이전 평면 구조 대비 크게 개선되었다.

| 항목 | 평가 |
| --- | --- |
| 패키지 경계 | 좋음. 역할별 폴더가 명확하다. |
| Application Layer 순수성 | 좋음. concrete infrastructure 의존을 제거했다. |
| DI 구조 | 좋음. FastAPI DI와 composition root가 분리되었다. |
| 테스트 안정성 | 좋음. 리팩토링 후 전체 테스트가 통과한다. |
| 모듈 응집도 | 보통. `services.py`, `repositories.py`, `schemas.py`가 아직 크다. |
| 도메인 순수성 | 보통. `domain/models.py`가 SQLAlchemy ORM 모델을 포함한다. |

점수로 보면 다음 정도다.

```text
패키지 구조 건강도: 8 / 10
레이어드 아키텍처 건강도: 7.5 / 10
```

## 남은 설계 이슈

### 1. 큰 파일 분리

다음 파일은 책임이 여러 개 섞여 있어 후속 PR에서 분리하는 것이 좋다.

```text
app/services/services.py
app/repositories/repositories.py
app/schemas/schemas.py
```

권장 분리 방향:

```text
app/services/
  analysis_service.py
  alert_policy.py
  scheduler_service.py

app/repositories/
  analysis_repository.py
  watchlist_repository.py
  alert_condition_repository.py

app/schemas/
  analysis.py
  market.py
  watchlist.py
  alert_conditions.py
```

### 2. ORM 모델 위치 재검토

현재 `app/domain/models.py`는 SQLAlchemy ORM 모델을 담고 있다. 실무적으로는 괜찮지만 엄격한 레이어드 아키텍처에서는 ORM 모델이 persistence detail에 가깝다.

도메인 로직이 커지면 다음 구조를 검토한다.

```text
app/domain/
  alert_conditions.py
  symbols.py
  analysis.py

app/repositories/models.py
  SQLAlchemy ORM models
```

### 3. Application workflow와 LLM adapter 경계

Gemini concrete adapter는 `app/integrations/llm/`에 둔다. 분석 graph와 custom rule context 수집 흐름은 `app/application/`에 둔다.

이후 LLM provider가 늘어나면 `app/integrations/llm/` 아래 provider별 adapter를 추가한다.

### 4. 설정 계층 통합

현재 설정은 `settings.py`, `scheduler_config.py`, `alert_config.py`, `kakao_settings()`에 분산되어 있다. 후속 작업에서 typed config object 중심으로 통합하는 것을 검토한다.

## 다음 PR 추천 순서

1. `services.py`를 유스케이스 단위로 분리한다.
2. `repositories.py`를 repository별 파일로 분리한다.
3. `schemas.py`를 데이터 계약별 파일로 분리한다.
4. ORM 모델 위치를 재검토한다.
5. 설정 계층을 typed config 중심으로 정리한다.

각 PR은 반드시 기존 테스트 통과를 완료 조건으로 둔다.

```powershell
.\.python311\python.exe -m pytest
```
