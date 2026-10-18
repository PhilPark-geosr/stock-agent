const test = require("node:test");
const assert = require("node:assert/strict");
const { BriefingPanel, renderBriefing, renderBriefingTargets } = require("../src/components/briefings/briefing-panel");

test("briefing evidence and model output are escaped and unsafe links are not clickable", () => {
  const output = renderBriefing({trade_date: "2026-09-21", purpose: "pre_market", status: "partial",
    context: {n: 2, cutoff_at: "2026-09-21T00:00:00Z"}, delivery: {status: "unknown"},
    prompt_content: "<script>instruction</script>",
    result: {summary: '<img src=x onerror="attack()">', items: [{symbol: "AAPL", verdict: "보류",
      reason: "<script>bad</script>", comparison: "비교 불가", comparison_reason: "처음",
      evidence_ids: ["news:1"], limitations: ["<unsafe>"], next_observation: "거래량"}]},
    snapshot: {evidence: [{id: "news:1", kind: "news", source: '"onclick="bad', url: "javascript:bad()",
      published_at: "2026-09-20", text: "<b>news</b>"}], sources: [], excluded: []}});
  assert.ok(!output.includes("<script>"));
  assert.ok(!output.includes("<img"));
  assert.ok(!output.includes('href="javascript:'));
  assert.match(output, /&lt;b&gt;news/);
  assert.match(output, /data-redeliver/);
  assert.match(output, /전송 결과 확인 불가/);
});

test("target picker keeps explicit selection and escapes stock identifiers", () => {
  const output = renderBriefingTargets(["005930.KS", "000660.KS", '<script>bad</script>'], new Set(["005930.KS"]));
  assert.match(output, /data-target-symbol="005930.KS" checked/);
  assert.doesNotMatch(output, /data-target-symbol="000660.KS" checked/);
  assert.doesNotMatch(output, /<script>/);
  assert.match(renderBriefingTargets([], new Set()), /관심종목이 아직 없어요/);
  assert.match(renderBriefingTargets(["AAPL"], new Set(), "MSFT"), /일치하는 관심종목이 없습니다/);
});

test("briefing setup exposes independent schedules and required trading-day count", () => {
  const output = BriefingPanel();
  for (const setting of ["pre_market_enabled", "post_market_enabled", "kakao_enabled"])
    assert.ok(output.includes(`name="${setting}"`));
  assert.match(output, /name="n"[^>]*required/);
  assert.match(output, /data-more-briefings/);
});


test("comparison provenance, original and failed-only retry are visible and escaped", () => {
  const run = {trade_date: "2026-09-21", purpose: "post_market", status: "partial",
    context: {n: 2, cutoff_at: "now"}, retryable_symbols: ["<failed>"],
    previous: {trade_date: "2026-09-21", purpose: "pre_market", n: 2, cutoff_at: "<cutoff>", verdicts: {AAPL: "매도"}},
    original: {trade_date: "<date>", purpose: "post_market"},
    result: {summary: "결과", items: [{symbol: "AAPL", verdict: "매수", reason: "근거", comparison: "변경",
      comparison_reason: "변화", evidence_ids: [], limitations: [], next_observation: "관찰"}]}};
  const output = renderBriefing(run);
  for (const marker of ["data-previous-briefing", "data-original-briefing", "data-retry-failed", "판단 변경 종목 우선", "이전 판단 매도 → 현재 판단 매수"])
    assert.ok(output.includes(marker));
  assert.match(output, /&lt;cutoff&gt;/);
  assert.match(output, /&lt;failed&gt;/);
  assert.match(output, /&lt;date&gt;/);
  assert.doesNotMatch(renderBriefing({...run, retryable_symbols: []}), /data-retry-failed/);
});
