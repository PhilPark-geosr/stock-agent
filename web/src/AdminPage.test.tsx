import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AdminPage } from './AdminPage';
import { ApiError, type WebApi } from './api';

const operator = { id: 'operator-account', login_provider: 'kakao', is_operator: true, has_beta_access: false };

function apiWith(issue: WebApi['issue']): WebApi {
  return {
    session: vi.fn(),
    login: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
    issue,
    redeem: vi.fn(),
    watchlist: vi.fn(),
    addWatchlist: vi.fn(),
    removeWatchlist: vi.fn(),
    analysisHistory: vi.fn(),
    analysisDetail: vi.fn(),
    runAnalysis: vi.fn(), alertConditions: vi.fn(), addAlertCondition: vi.fn(), removeAlertCondition: vi.fn(),
    notificationConnection: vi.fn(), authorizeNotification: vi.fn(), disconnectNotification: vi.fn(),
  };
}

describe('admin invitation issuance', () => {
  it('blocks duplicate issuance, displays the code and Korean expiry, and copies the code', async () => {
    let finish!: (value: { code: string; expires_at: string }) => void;
    const issue = vi.fn().mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const copyText = vi.fn().mockResolvedValue(undefined);

    render(
      <AdminPage
        api={apiWith(issue)}
        session={operator}
        onLogout={vi.fn()}
        onSessionExpired={vi.fn()}
        copyText={copyText}
      />,
    );

    const issueButton = screen.getByRole('button', { name: '초대 코드 발급' });
    fireEvent.click(issueButton);
    expect(issueButton).toBeDisabled();
    fireEvent.click(issueButton);
    expect(issue).toHaveBeenCalledTimes(1);

    finish({ code: 'invite-once', expires_at: '2030-01-01T15:00:00Z' });
    expect(await screen.findByTestId('invitation-code')).toHaveTextContent('invite-once');
    expect(screen.getByText(/한국 시간/)).toHaveTextContent(/2030.*1.*2/);

    fireEvent.click(screen.getByRole('button', { name: '코드 복사' }));
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('invite-once'));
  });

  it('shows an issuance failure and leaves retry as an explicit user action', async () => {
    const issue = vi.fn().mockRejectedValue(new ApiError(500));
    render(
      <AdminPage
        api={apiWith(issue)}
        session={operator}
        onLogout={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '초대 코드 발급' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('발급');
    expect(issue).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '초대 코드 발급' })).toBeEnabled();
    expect(screen.queryByTestId('invitation-code')).not.toBeInTheDocument();
  });

  it('returns to signed-out state when the server reports an expired session', async () => {
    const onSessionExpired = vi.fn();
    render(
      <AdminPage
        api={apiWith(vi.fn().mockRejectedValue(new ApiError(401)))}
        session={operator}
        onLogout={vi.fn()}
        onSessionExpired={onSessionExpired}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '초대 코드 발급' }));
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });

  it('reports revoked operator access without treating the session as signed out', async () => {
    const onSessionExpired = vi.fn();
    render(
      <AdminPage
        api={apiWith(vi.fn().mockRejectedValue(new ApiError(403)))}
        session={operator}
        onLogout={vi.fn()}
        onSessionExpired={onSessionExpired}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '초대 코드 발급' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('운영자 권한');
    expect(onSessionExpired).not.toHaveBeenCalled();
  });
});
