# 연속 브리핑 구현·실행 기록

2026-09-21 · 기준 설계: [확정 OOD v1.0](../design/continuous_briefing_design.md)

`upstream/main`의 `12ba6a4`(PR #33 반영)를 가져온 뒤 `codex/continuous-briefing` 브랜치에서 구현했다. 기존 작업 디렉터리의 수정사항을 보존하기 위해 `.codex-worktrees/continuous-briefing`에서 작업했다. 사용자는 초안 가정과 OOD를 이미 수용했으며, 구현 중 공개자료 범위를 **뉴스와 공식 공시 모두**로 확인했다.

## 실행

아래 명령은 이 구현이 있는 작업 디렉터리에서 실행한다. 기존 DB를 사용한다면 업그레이드 전에 백업한다. `.env`에는 실제 값을 로컬에서 설정하고 저장소에 커밋하지 않는다.

```powershell
uv sync
Copy-Item .env.example .env  # .env가 없는 최초 설정 때만
```

| 설정 | 용도 |
| --- | --- |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | 브리핑 분석과 지침 미리보기 |
| `DART_API_KEY` | 한국 종목 공식 공시 조회 |
| `SEC_USER_AGENT` | 미국 공시 조회 시 앱·운영자 이름과 연락 이메일 (예: `MyStockAgent contact@example.com`) |
| 기존 Kakao 키·리다이렉트·`NOTIFICATION_TOKEN_FERNET_KEY` | 기존 로그인·사용자별 카카오 수신 연결 재사용 |
| `BRIEFING_SCHEDULER_ENABLED=true` | 브리핑 자동 실행. 기존 조건 알림의 `SCHEDULER_ENABLED`와 독립 |
| `DATABASE_URL` | API·스케줄러·지침 CLI가 함께 사용하는 DB |

공시 설정이 없으면 해당 출처를 ‘연결 설정 필요’로 표시하고 부분 브리핑으로 남긴다. 설정 누락을 ‘공시 없음’으로 바꾸지 않는다. 모델 키가 없으면 분석을 성공으로 처리하지 않는다.

먼저 공통 지침을 미리보고 적용한다. 미리보기는 실제 시장 자료가 아닌 고정 예제를 Gemini로 분석하며 API 사용량이 발생한다. 브리핑 이력이나 카카오 메시지는 만들지 않는다. 이전 적용 지침과의 차이도 출력한다.

```powershell
uv run python -m app.cli.briefing_prompt preview
uv run python -m app.cli.briefing_prompt activate <미리보기의-version>
uv run python -m app.cli.briefing_prompt status
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

CLI와 앱 시작 시 Alembic `0010_briefing_targets`까지 마이그레이션한다. `0009`는 브리핑 저장 구조를, `0010`은 사용자별 대상 선택을 추가한다. 이후 Electron 클라이언트를 실행한다.

```powershell
cd desktop-demo
npm ci
npm start
```

로그인 → 관심종목 등록 → **투자 브리핑**에서 분석할 종목과 n거래일을 선택 → 생성 조건과 수신 상태 확인 → 장전/장후 브리핑 생성. 장전·장후 자동 제공과 카카오 수신은 각각 따로 저장한다. 카카오 수신 연결은 기존 알림 기능에서 연결한다. 생성 결과와 전송 상태를 별도로 확인하며, 과거 브리핑에서는 당시 근거·일봉·지침을 확인할 수 있다.

## 관심종목 선택과 화면 흐름 (FR-C17)

- 시장별 본인 관심종목을 검색·개별 선택·전체 선택·해제하며, 선택 개수를 확인한다. 저장한 선택이 없으면 사용자가 먼저 고른다. 관심종목이 없으면 등록 화면으로 이동할 수 있다.
- 기간은 직접 입력하거나 20/60/120거래일 버튼으로 선택한다. 임의의 기본 기간을 넣지 않는다. 생성 가능 시간과 지침·공시·카카오 연결 상태를 생성 전에 안내한다.
- 이번 수동 분석 대상을 바꿔도 자동 제공 설정은 바뀌지 않는다. 별도 설정 영역에서 현재 선택과 기간을 저장해야 자동 제공에 반영된다.
- 지정 대상을 저장한 뒤 추가한 관심종목은 자동 포함하지 않는다. 삭제한 대상은 다음 실행에서 제외하며, 남은 대상이 없으면 생성하지 않는다. 기존 설정에 대상 목록이 없으면 이전의 전체 관심종목 동작을 유지한다.
- 과거 브리핑의 ‘이 종목으로 새 브리핑 준비’는 조건만 불러온다. 사용자가 현재 대상과 조건을 확인한 뒤 생성한다.
- 서버가 선택 목록의 소유권·시장·활성 구독을 검증한다. 빈 배열·중복·미등록 대상은 거절하고 기존 브리핑의 입력은 바꾸지 않는다.

관심종목 등록 화면의 개발자용 API 문구를 사용자 안내로 바꾸었다. 영문 티커에 `.KS`를 붙이던 등록 경로도 수정해 6자리 숫자 코드만 기본 코스피 심볼로 변환한다.

수정할 때는 `prompt.md` 편집 → `preview` → `activate`를 반복한다. 파일을 수정하기만 해서는 적용 판본을 바꾸지 않는다. 파일이 없거나 읽을 수 없어도 마지막 적용 판본을 유지하며 `status`에서 차이를 확인한다. 적용 판본이 한 번도 없었다면 생성을 시작하지 않는다.

```powershell
uv run python -m app.cli.briefing_prompt rollback <과거에-검증된-version>
```

## 구현 중 구체화한 정책

| 결정 | 동작·한계 | 근거 |
| --- | --- | --- |
| 거래일·시장 | 한국 `.KS/.KQ`는 XKRX, 미국 티커는 XNYS 거래일·개폐장 달력을 사용. 다른 시장은 현재 지원하지 않음 | FR-C01/C02/C11 |
| 수동 생성 시각 | 거래일의 개장 전 장전 생성, 마감 15분 뒤 장후 생성. 휴장일은 생성 요청 거절 | FR-C01/C02/C05 |
| 자동 제공 | 장전 개장 30분 전부터 개장까지, 장후 마감 15분 후부터 마감 2시간 후까지 30초 주기로 확인. 해당 사용자·시장·거래일·목적당 1회 예약 | FR-C11/C14 |
| 실행 조건 | 백엔드가 켜져 있어야 함. 꺼져 있던 기간을 소급해 과거 브리핑처럼 생성하지 않음. 실패한 정기 요청은 같은 날 자동 재분석하지 않고 이력에서 새 분석 요청 | FR-C08/C14 |
| n·용량 | n은 요청 또는 저장 설정에서 필수, 1~250거래일. 시장당 30종목, 모델 입력 600KB. 초과하면 기간·대상을 몰래 줄이지 않고 명시적 실패 | FR-C01/C02/C16 |
| 차트 | Yahoo 일봉 OHLCV, 배당·분할 미조정. 거래소 달력의 최근 n개 세션만 사용. 장후는 당일 종가 자료가 없는 종목을 보류 | FR-C02/C05 |
| 뉴스 | Yahoo 최근 최대 50건에서 시점·대상을 검증. 제목·제공 요약·원문 링크를 저장. 기간 전체의 완전한 뉴스 수집을 보장하지 않아 부분 수집으로 표시 | FR-C04/C05 |
| 공식 공시 | 한국 DART, 미국 SEC recent 제출 목록. 기간 내 최근 최대 5건의 원문 앞부분 6,000자까지 발췌. 그 외는 제목·출처·링크. 전체 보고서/첨부파일을 분석한 것으로 표시하지 않음 | FR-C04/C05 |
| 공시 시각 | DART 접수일만 있는 자료는 접수일 종료 시점을 보수적 상한으로 사용. 당일 공시는 확정 시각을 알 수 없어 제외. SEC는 공급자의 acceptanceDateTime을 사용 | FR-C04/C08 |
| 자료 한도 | 종목당 공개자료 20건. 뉴스·공시 각 최신 10건을 우선 확보하고 남는 자리는 다른 종류로 채움. 제외 건수와 수집 오류를 보존 | FR-C04/C05/C16 |
| SEC 요청 | 앱과 연락 이메일을 User-Agent에 넣고 프로세스 전체 요청 간격 0.2초 적용. 여러 서버 운영 시 IP 전체 요청량을 별도로 제한해야 함 | 공급자 연동 구체화 |
| 직전 비교 | 같은 사용자·시장·오늘 또는 직전 거래일의 완료/부분 완료 중 시점과 종목이 겹치는 결과. 장후는 오늘 장전 우선. 더 오래된 기록을 자동 순회하지 않음 | FR-C03/C10 |
| 입력 고정 | 대상·n·시점·지침·직전 결과 고정, 수집 자료와 분석 결과를 보존. 지침 변경·관심종목 삭제가 과거 내용을 바꾸지 않음 | FR-C08/C09 |
| 재분석·재전달 | 재분석은 현재 시점의 새 실행과 원본 참조를 생성. 재전달은 저장된 메시지 사용, 모델 호출 없음 | FR-C09/C13/C14 |
| 결과·알림 분리 | 결과와 전달 대기를 한 DB 트랜잭션으로 저장한 후 발송. 실패는 결과를 취소하지 않음. 연결·수신 설정을 발송 직전 재확인 | FR-C12/C13/C15 |
| 중복·복구 | DB 유일 예약, 생성 소유권 10분·수집 단계 갱신, 전송 소유권 5분·전달 버전 검사. 입력 스냅샷이 있으면 중단 작업 인계, 없으면 실패 | FR-C08/C14 |
| 전송 불명 | 응답 유실·전송 중 프로세스 종료는 ‘확인 불가’. 자동 재전송 금지. 중복 도착 가능성을 확인한 명시적 재전달만 허용 | FR-C13/C14 |
| 요청 대기 | 수동 생성은 동기 API. Electron 생성 요청은 최대 30분 기다림. 연결이 끊겨도 같은 요청 번호로 조회/재요청하면 재분석을 중복 시작하지 않음 | FR-C14 |

공급자 근거: [Open DART 공시검색](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001), [Open DART 제공자료 소개](https://opendart.fss.or.kr/intro/main.do), [SEC EDGAR 접근 안내](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), [yfinance 뉴스 API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.get_news.html).

yfinance의 `get_news()`가 잘못된 응답을 빈 목록으로 바꾸는 경우가 있어, 뉴스 어댑터는 같은 쿠키 처리 전송기를 사용하되 HTTP 상태와 실제 뉴스 목록 구조를 직접 검증한다. 이 부분은 yfinance 내부 전송기와 Yahoo 응답 형식에 의존하므로 라이브러리 업그레이드 시 어댑터 테스트와 실제 조회를 함께 확인한다. 차트 조회도 오류를 숨기지 않도록 예외 발생 옵션을 사용한다.

## 설계와 코드 추적

| 구현 | 책임 | 추적 |
| --- | --- | --- |
| `app/domain/briefings.py` | 맥락·근거·출력·오류 계약 | UC-C01~C05, FR-C01~C16 |
| `app/integrations/briefing_calendar.py` | 사용자 대상·거래일·n·제공 시각 | FR-C01/C02/C10/C11 |
| `app/application/briefings.py` | 생성 조율·재분석·복구 | FR-C01/C08/C09/C13/C14 |
| `app/application/briefing_evidence.py`, `app/integrations/briefing_sources.py` | 출처·시점 검증, 뉴스·공시·차트 수집 | FR-C02/C04/C05 |
| `app/application/briefing_analysis.py`, `app/integrations/llm/gemini_briefing_model.py` | 출력 검증·판단 비교·제약 유지 | FR-C03/C05/C06/C10/C16 |
| `app/application/briefing_prompts.py`, `app/cli/briefing_prompt.py` | 지침 미리보기·적용·롤백 | UC-C04, FR-C07~C09 |
| `app/repositories/briefings.py`, `app/domain/briefing_records.py`, migration 0009 | 사용자별 불변 이력·원자적 예약·전달 대기 | FR-C08~C10/C13/C14 |
| `app/application/briefing_delivery.py` | 카카오 전달·재전달·불명 상태 | UC-C05, FR-C12~C15 |
| `app/api/briefings.py`, `app/core/briefing_runtime.py` | 인증 경계·이력·설정·정기 실행 | UC-C01~C03/C05, FR-C10/C11/C14 |
| Electron 브리핑 화면·컨트롤러 | 생성·이력·수집 한계·지침 확인·재전달 | UC-C01~C03/C05 |

사람 액터와 사용자 목표, Essential Style 명세, 관계 중심 초기 시퀀스는 확정 설계 문서에 그대로 둔다. 위 구현 매핑을 유스케이스 다이어그램에 추가하지 않는다.

## API

모두 기존 Bearer 로그인 필요. 소유자는 요청 본문에서 받지 않고 인증 계정으로 결정한다.

- `GET/PUT /briefings/settings/{KR|US}`: n, 지정 대상 `symbols`, 장전·장후 자동 제공, 카카오 수신 설정
- `GET /briefings/options/{KR|US}`: 본인 관심종목, 생성 가능 시간, 지침·공시·카카오 설정 준비 상태. 키나 토큰은 반환하지 않는다.
- `POST /briefings`: `request_id`, `market`, `purpose`, 선택적 `n`, 선택적 `symbols`, 선택적 `original_id`. 화면은 선택한 `symbols`를 명시적으로 보낸다.
- `GET /briefings?limit=30&offset=0`: 본인 이력 (화면에서 이전 이력 더 보기 가능)
- `GET /briefings/{id}`: 본인 결과·원본 입력·적용 지침·전달 이력
- `POST /briefings/{id}/delivery`: 재전달용 `request_id`, 불명 결과 시 `acknowledge_unknown=true`

## 검증과 실제 연동 범위

최종 자동 검증: **Python 113개 통과, Electron JavaScript 22개 통과, JavaScript 문법 검사 통과**. Python 실행에는 기존 라이브러리의 폐기 예정 경고 5건이 있으나 실패는 없다.

```powershell
uv run pytest -q
cd desktop-demo
npm test
npm run check
```

새 테스트는 첫 브리핑·오늘 장전 우선·직전 거래일 비교, 입력 보존, 지침 변경 중 실행·롤백, 휴장·조기 마감, 뉴스/공시 시점·용량·원문 수집, 권한 격리, 별도 DB 연결 간 동시 예약/발송, 스케줄러 사용자별 실패 격리, 전달 대기 복구, 중단·불명 전송, 출력 오류 재시도, 화면 출처·모델 출력의 HTML 이스케이프를 검증한다. 기존 테스트도 함께 실행한다.

자동 테스트의 외부 HTTP는 대역으로 검증했다. 로컬 앱 실행·카카오 로그인과, 사용자 승인 후 Gemini 고정 예제 검증·지침 적용을 확인했다. 이는 실제 투자자료 분석·공시 공급자 실연동·카카오 발송의 전체 검증을 뜻하지 않는다. 로컬 키·DB·로그·화면 캡처는 커밋하지 않는다.

실행 DB를 백업하고 `0009`에서 `0010`으로 업그레이드한 뒤 실제 Electron에서 등록 종목 선택, 선택 해제 시 생성 차단, 980px 화면의 한 열 배치를 확인했다. UI 검증에서는 분석 생성·카카오 발송·설정 저장을 실행하지 않았다.

공시 원문 일부 발췌·DART 당일 공시 제외·고정 제공 시간은 현재 동작의 제약이다. 입력 크기 초과 시 요약 없이 실패하는 동작, 정상 공시 0건의 부분 수집 표시, 과거 비교 근거 화면 등 미완성 항목은 [설계 대비 점검](continuous_briefing_design_audit_2026-09-21.md)에 기록했다. 이번 대상 선택 개선은 이 분석 정책을 변경하지 않는다.
