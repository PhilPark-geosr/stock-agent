import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BetaAppPage } from './BetaAppPage';
import { ApiError, type AnalysisHistoryItem, type WebApi } from './api';

const session = { id: 'member', login_provider: 'kakao', is_operator: false, has_beta_access: true };
const msftHistory: AnalysisHistoryItem[] = [{ id: 1, symbol: 'MSFT', analyzed_at: '2030-01-01T00:00:00Z', data_timestamp: null, overall_judgment: '관망', summary: '이전 종목 결과', should_alert: false, triggered_alerts: [], shared_safe: true }];

function apiWith(history: WebApi['analysisHistory']): WebApi {
  return {
    session: vi.fn(), login: vi.fn(), logout: vi.fn(), issue: vi.fn(), redeem: vi.fn(),
    watchlist: vi.fn().mockResolvedValue([{ id: 1, symbol: 'MSFT', created_at: '' }, { id: 2, symbol: 'AAPL', created_at: '' }]),
    addWatchlist: vi.fn(), removeWatchlist: vi.fn(), analysisHistory: history, analysisDetail: vi.fn(),
    runAnalysis: vi.fn(), alertConditions: vi.fn().mockResolvedValue([]), addAlertCondition: vi.fn(),
    removeAlertCondition: vi.fn(), notificationConnection: vi.fn().mockResolvedValue({ connected: false, connection_id: null }),
    authorizeNotification: vi.fn(), disconnectNotification: vi.fn(),
  };
}

describe('saved analysis selection', () => {
  it('does not show an earlier symbol history after selection changes and the new request fails', async () => {
    let resolveMsft!: (items: AnalysisHistoryItem[]) => void;
    let rejectAapl!: (error: Error) => void;
    const api = apiWith(vi.fn().mockImplementation((symbol: string) => symbol === 'MSFT'
      ? new Promise<AnalysisHistoryItem[]>(resolve => { resolveMsft = resolve; })
      : new Promise<AnalysisHistoryItem[]>((_resolve, reject) => { rejectAapl = reject; }),
    ));
    render(<BetaAppPage api={api} session={session} onLogout={vi.fn()} onSessionExpired={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'AAPL 선택' }));
    resolveMsft(msftHistory);
    await waitFor(() => expect(api.analysisHistory).toHaveBeenCalledWith('AAPL'));
    expect(screen.queryByText('이전 종목 결과')).not.toBeInTheDocument();
    rejectAapl(new ApiError(500));
    expect(await screen.findByRole('alert')).toHaveTextContent('저장된 분석 이력을 불러오지 못했습니다');
    expect(screen.queryByText('이전 종목 결과')).not.toBeInTheDocument();
  });

  it('does not leave the next symbol detail actions disabled when an earlier detail request stalls', async () => {
    let resolveOldDetail!: (value: Awaited<ReturnType<WebApi['analysisDetail']>>) => void;
    const oldHistory: AnalysisHistoryItem[] = [{ ...msftHistory[0], summary: 'MSFT stored result' }];
    const newHistory: AnalysisHistoryItem[] = [{ ...msftHistory[0], id: 2, symbol: 'AAPL', summary: 'AAPL stored result' }];
    const api = apiWith(vi.fn().mockImplementation((symbol: string) => Promise.resolve(symbol === 'MSFT' ? oldHistory : newHistory)));
    api.analysisDetail = vi.fn().mockImplementation(() => new Promise(resolve => { resolveOldDetail = resolve; }));
    render(<BetaAppPage api={api} session={session} onLogout={vi.fn()} onSessionExpired={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'AAPL 선택' }));
    const nextDetail = await screen.findByText('AAPL stored result');
    expect(nextDetail.closest('button')).toBeEnabled();
    fireEvent.click(nextDetail.closest('button')!);
    expect(api.analysisDetail).toHaveBeenCalledWith('AAPL', 2);

    resolveOldDetail({ ...oldHistory[0], key_reasons: [], risk_factors: [], support_levels: {}, alert_reason: null, raw_result: null });
  });

  it('does not allow an add that a still-loading watchlist response could overwrite', async () => {
    let resolveWatchlist!: (items: Awaited<ReturnType<WebApi['watchlist']>>) => void;
    const api = apiWith(vi.fn());
    api.watchlist = vi.fn().mockImplementation(() => new Promise(resolve => { resolveWatchlist = resolve; }));
    render(<BetaAppPage api={api} session={session} onLogout={vi.fn()} onSessionExpired={vi.fn()} />);

    expect(await screen.findByRole('button', { name: '종목 추가' })).toBeDisabled();
    resolveWatchlist([]);
  });

  it('shows the newest saved detail automatically and never calls the generating latest endpoint', async () => {
    const api = apiWith(vi.fn().mockResolvedValue(msftHistory));
    api.analysisDetail = vi.fn().mockResolvedValue({ ...msftHistory[0], key_reasons: ['매출 증가'], risk_factors: ['변동성'], support_levels: { latest_close: 50000, change_percent: 2.3, volume_ratio_20: 1.5, low_20: 48000, high_20: 52000 }, alert_reason: '시장 신호', raw_result: null });
    render(<BetaAppPage api={api} session={session} onLogout={vi.fn()} onSessionExpired={vi.fn()} />);
    expect(await screen.findByText('매출 증가')).toBeInTheDocument();
    expect(screen.getByText(/50,000/)).toBeInTheDocument();
    expect(api.analysisDetail).toHaveBeenCalledWith('MSFT', 1);
    expect(api.runAnalysis).not.toHaveBeenCalled();
  });

  it('shows an empty state and runs a shared analysis only after a click', async () => {
    const api = apiWith(vi.fn().mockResolvedValue([]));
    api.runAnalysis = vi.fn().mockResolvedValue({ ...msftHistory[0], key_reasons: ['새 근거'], risk_factors: [], support_levels: {}, alert_reason: null, raw_result: null });
    render(<BetaAppPage api={api} session={session} onLogout={vi.fn()} onSessionExpired={vi.fn()} />);
    expect(await screen.findByText(/저장된 분석이 없습니다/)).toBeInTheDocument();
    expect(api.runAnalysis).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '수동 분석 실행' }));
    expect(await screen.findByText('새 근거')).toBeInTheDocument();
    expect(api.runAnalysis).toHaveBeenCalledWith('MSFT');
  });

  it('keeps a completed manual result when refreshing history fails', async () => {
    const result = { ...msftHistory[0], id: 7, summary: '새 분석 결과', key_reasons: ['새 근거'], risk_factors: [], support_levels: {}, alert_reason: null, raw_result: null };
    const api = apiWith(vi.fn().mockResolvedValueOnce([]).mockRejectedValueOnce(new ApiError(500)));
    api.runAnalysis = vi.fn().mockResolvedValue(result);
    render(<BetaAppPage api={api} session={session} onLogout={vi.fn()} onSessionExpired={vi.fn()} />);
    await screen.findByText(/저장된 분석이 없습니다/);
    fireEvent.click(screen.getByRole('button', { name: '수동 분석 실행' }));
    expect(await screen.findByText('새 근거')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('공통 분석이 저장되었습니다');
    expect(screen.getByRole('alert')).toHaveTextContent('분석 이력을 갱신하지 못했습니다');
    expect(screen.getByRole('list', { name: 'MSFT 저장된 분석 이력' })).toHaveTextContent('새 분석 결과');
  });
});
