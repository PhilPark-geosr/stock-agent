import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AnalysisHistoryPanel, AnalysisPanel } from './components/AnalysisPanels';
import type { AnalysisResult } from './api';

const result: AnalysisResult = {
  id: 1, symbol: '005930.KS', analyzed_at: '2026-11-08T23:10:00Z',
  data_timestamp: '2026-11-05T15:00:00Z',
  chart_basis: { interval: '1d', session_date: '2026-11-06', source_timezone: 'Asia/Seoul', finality: 'unknown' },
  overall_judgment: '중립', summary: '금요일 기준 판단', should_alert: false,
  triggered_alerts: [], shared_safe: true, key_reasons: [], risk_factors: [],
  support_levels: { latest_close: 72000 }, alert_reason: null, raw_result: null,
};

describe('analysis time meaning', () => {
  it('keeps the session date beside the saved price and the Monday record time in KST', () => {
    const { rerender } = render(<AnalysisPanel symbol={result.symbol} detail={result} latestId={2} loading={false} running={false} onRun={vi.fn()} />);
    expect(screen.getByText('2026-11-06 일봉 기준 · 시장 현지일')).toBeVisible();
    expect(screen.getByText('수집 시점 상태 미확인')).toBeVisible();
    expect(screen.getByText(/분석 기록.*2026\. 11\. 9\..*KST/)).toBeVisible();
    expect(screen.getByText('일봉 기준 가격')).toBeVisible();
    expect(screen.queryByText(/시장 데이터 시각/)).not.toBeInTheDocument();
    rerender(<AnalysisHistoryPanel symbol={result.symbol} items={[result]} selectedId={1} loading={false} detailLoading={null} hasMore={false} onSelect={vi.fn()} onLatest={vi.fn()} onMore={vi.fn()} />);
    expect(screen.getByText('2026-11-06 일봉 기준 · 시장 현지일')).toBeVisible();
    expect(screen.getByText(/분석 기록.*2026\. 11\. 9\..*KST/)).toBeVisible();
  });

  it('shows unknown for legacy metadata even when a data timestamp exists', () => {
    render(<AnalysisPanel symbol={result.symbol} detail={{ ...result, chart_basis: null }} latestId={1} loading={false} running={false} onRun={vi.fn()} />);
    expect(screen.getByText('가격 기준 거래일 미확인')).toBeVisible();
    expect(screen.queryByText('마감 확정 여부 미확인')).not.toBeInTheDocument();
    expect(screen.getByText('분석 기준 가격')).toBeVisible();
  });

  it('distinguishes failed history retrieval from a successful empty result', () => {
    render(<AnalysisHistoryPanel symbol={result.symbol} items={[]} selectedId={null} loading={false} detailLoading={null} hasMore={false} onSelect={vi.fn()} onLatest={vi.fn()} onMore={vi.fn()} error="이력을 불러오지 못했습니다." />);
    expect(screen.getByText('이력을 불러오지 못했습니다.')).toBeVisible();
    expect(screen.queryByText('저장된 분석 이력이 없습니다.')).not.toBeInTheDocument();
  });

  it.each([
    ['during_session', '장중 기준'],
    ['after_session', '정규장 종료 후 수집'],
    ['boundary', '장 마감 경계에서 수집'],
  ] as const)('renders stored %s in detail and history without using the current clock', (phase, label) => {
    const saved = { ...result, chart_basis: { ...result.chart_basis!, collection_phase: phase, collected_at: '2026-11-06T06:31:00Z' } };
    const { rerender } = render(<AnalysisPanel symbol={saved.symbol} detail={saved} latestId={2} loading={false} running={false} onRun={vi.fn()} />);
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.getByText(/가격 수집 완료.*KST/)).toBeVisible();
    if (phase === 'after_session') expect(screen.getByText('공급자의 마감 가격 반영은 확인되지 않았습니다.')).toBeVisible();
    rerender(<AnalysisHistoryPanel symbol={saved.symbol} items={[saved]} selectedId={1} loading={false} detailLoading={null} hasMore={false} onSelect={vi.fn()} onLatest={vi.fn()} onMore={vi.fn()} />);
    expect(screen.getByText(label)).toBeVisible();
  });

  it('explains a calendar failure instead of suggesting a closing price', () => {
    render(<AnalysisPanel symbol={result.symbol} detail={{ ...result, chart_basis: { ...result.chart_basis!, phase_reason: 'calendar_unavailable' } }} latestId={1} loading={false} running={false} onRun={vi.fn()} />);
    expect(screen.getByText('거래소 일정을 확인하지 못했습니다.')).toBeVisible();
  });
});
