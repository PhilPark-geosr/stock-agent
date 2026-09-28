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

    fireEvent.click(await screen.findByRole('button', { name: 'AAPL 분석 이력' }));
    resolveMsft(msftHistory);
    await waitFor(() => expect(api.analysisHistory).toHaveBeenCalledWith('AAPL'));
    expect(screen.queryByText('이전 종목 결과')).not.toBeInTheDocument();
    rejectAapl(new ApiError(500));
    expect(await screen.findByRole('alert')).toHaveTextContent('저장된 분석 이력을 불러오지 못했습니다');
    expect(screen.queryByText('이전 종목 결과')).not.toBeInTheDocument();
  });
});
