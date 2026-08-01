# Stock Analysis Context

The system analyzes a user's tracked listed securities and produces market-session briefings without performing trades or making guaranteed recommendations.

## Briefing Language

**Investment Briefing**:
A stored, user-owned collection of security analyses generated for one exchange, trading date, and briefing type.
_Avoid_: Alert, report, notification

**Pre-Market Briefing**:
An investment briefing whose comparison point is the latest valid prior analysis and whose market session has not opened.
_Avoid_: Morning report

**Post-Market Summary**:
An investment briefing based on confirmed closing data whose preferred comparison point is the same session's pre-market analysis.
_Avoid_: Closing alert

**Briefing Scope**:
The immutable snapshot of resolved securities included when an investment briefing is generated. Security search and filter resolution occur outside the briefing context.
_Avoid_: Search query, raw mention text

**Judgment Change**:
A comparable difference between the normalized current and previous investment judgments for the same user and security.
_Avoid_: Alert trigger, trade signal

**Delivery Attempt**:
A channel-specific effort to transmit an already stored investment briefing; its failure never changes the briefing's generation result.
_Avoid_: Briefing generation

**Trading Session**:
The exchange calendar's dated regular-trading interval, including holiday, early-close, timezone, and daylight-saving rules.
_Avoid_: Weekday, fixed UTC window
