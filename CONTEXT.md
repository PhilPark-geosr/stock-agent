# 주식 분석

여러 개인 투자자가 각자의 관심 종목과 알림 조건을 관리하고, 공유 종목 분석을 바탕으로 사용자별 투자 브리핑을 확인하는 서비스의 핵심 언어를 정의한다.

## Language

**Investment Briefing**:
A stored collection owned by one user account that selects and compares shared stock analyses for one exchange, trading date, and briefing type.
_Avoid_: Alert, report, notification

**Pre-Market Briefing**:
An investment briefing whose comparison point is the latest valid prior analysis and whose market session has not opened.
_Avoid_: Morning report

**Post-Market Summary**:
An investment briefing based on confirmed closing data whose preferred comparison point is the same session's pre-market analysis.
_Avoid_: Closing alert

**Briefing Scope**:
The immutable snapshot of resolved securities for one completed investment-briefing version. A retention policy may discard an older version as a whole, but a retained version's scope is never reinterpreted. Security search and filter resolution occur outside the briefing context.
_Avoid_: Search query, raw mention text

**Judgment Change**:
A comparable difference between normalized current and previous judgments for the same stock. The comparison is shared market analysis; its inclusion and presentation belong to a user's investment briefing.
_Avoid_: Alert trigger, trade signal

**Delivery Attempt**:
A channel-specific effort to transmit an already stored investment briefing; its failure never changes the briefing's generation result.
_Avoid_: Briefing generation

**Trading Session**:
The exchange calendar's dated regular-trading interval, including holiday, early-close, timezone, and daylight-saving rules.
_Avoid_: Weekday, fixed UTC window
**사용자 계정(User Account)**:
개인 투자자를 서비스 안에서 식별하며 관심 종목, 알림 조건과 알림 수신 설정의 소유권 기준이 되는 계정.
_Avoid_: User, 개인 투자자, 운영자, 로컬 사용자

**로그인 신원(Login Identity)**:
로그인 제공자와 그 제공자가 부여한 사용자 식별자의 조합으로, 하나의 사용자 계정이 외부에서 확인된 사람과 대응되게 하는 값. 사용자 계정이 소유하며 독립적인 생명주기를 갖지 않는다.
_Avoid_: External Identity, 사용자 계정, 로그인 제공자, 알림 연결, 카카오 알림 토큰

**알림 연결(Notification Connection)**:
사용자가 외부 알림 채널을 통해 메시지를 받을 수 있도록 서비스에 부여한 연결 상태. 로그인 상태와는 독립적이며 연결이 해제되어도 사용자 계정과 분석 정보는 유지된다.
_Avoid_: 로그인, 사용자 인증

**종목 분석(Stock Analysis)**:
특정 시점의 시장 데이터를 근거로 생성되며 같은 종목을 보는 모든 사용자에게 공통으로 제공되는 분석 결과. 사용자의 알림 조건이나 개인 설정에 따라 내용이 달라지지 않는다.
_Avoid_: 사용자 분석, 맞춤 분석

**시스템 시장 신호(System Market Signal)**:
급등락이나 거래량 급증처럼 공유 종목 분석에서 공통으로 탐지된 주의 신호. 특정 사용자가 소유하지 않으며, 신호의 탐지와 사용자별 알림 전달은 서로 다른 개념이다.
_Avoid_: 사용자 알림 조건, 알림 발송

**사용자 알림 조건(User Alert Condition)**:
특정 사용자가 소유하며 어떤 시장 상황에서 알림받을지를 표현한 조건. 종목 분석의 내용을 바꾸지 않는다.
_Avoid_: 분석 프롬프트, 시스템 알림 조건

**관심 종목 구독(Watchlist Subscription)**:
한 사용자 계정이 하나의 종목 코드를 지속적으로 관찰하겠다는 독립적인 관계. 시작과 종료의 생명주기를 가지며, 종료된 종목을 다시 구독하면 과거 관계가 아닌 새로운 관계가 성립한다.
_Avoid_: 관심 종목 목록, 종목, 사용자 계정의 구독 컬렉션

**종목 코드(Stock Symbol)**:
외부 시장에서 분석 및 구독 대상을 식별하는 정규화된 값. 독립적인 생명주기를 갖는 종목 엔티티가 아니라 코드 자체의 값으로 동일성을 판단한다.
_Avoid_: Stock 엔티티, 종목 ID, 관심 종목 구독

**알림 평가(Alert Evaluation)**:
종목 분석과 시장 정보를 근거로 한 사용자의 알림 조건이 충족되었는지 판단한 결과. 사용자별로 생성되며 종목 분석과 분리된다.
_Avoid_: 종목 분석, 알림 발송
