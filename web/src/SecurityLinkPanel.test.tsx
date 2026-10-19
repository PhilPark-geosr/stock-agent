import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError, type WebApi } from './api';
import { SecurityLinkPanel } from './components/SecurityLinkPanel';

const item = { id: 7, symbol: 'MSFT', created_at: '2026-10-01', security_id: null };
const candidate = { symbol: 'MSFT', name: 'Microsoft', country: 'US', note: 'NASDAQ · 보통주', source_date: '2026-10-19', security_id: 'security', selectable: true };
function fixture(overrides: Partial<WebApi> = {}) {
  const api = { securityCandidates: vi.fn().mockResolvedValue([candidate]), linkWatchlist: vi.fn().mockResolvedValue({ ...item, security_id: 'security' }), ...overrides } as unknown as WebApi;
  const onLinked = vi.fn();
  render(<SecurityLinkPanel item={item} api={api} onLinked={onLinked} onSessionExpired={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'MSFT 종목 정보 연결' }));
  return { api, onLinked };
}

describe('legacy subscription confirmation', () => {
  it('requires choosing a candidate and explicit confirmation and returns the same subscription', async () => {
    const { api, onLinked } = fixture();
    const radio = await screen.findByRole('radio');
    expect(radio).not.toBeChecked();
    expect(screen.getByRole('button', { name: '같은 종목임을 확인하고 연결' })).toBeDisabled();
    fireEvent.click(radio);
    fireEvent.click(screen.getByRole('button', { name: '같은 종목임을 확인하고 연결' }));
    await waitFor(() => expect(api.linkWatchlist).toHaveBeenCalledWith(7, 'MSFT', 'security'));
    await waitFor(() => expect(onLinked).toHaveBeenCalledWith(expect.objectContaining({ id: 7, security_id: 'security' })));
  });

  it('cancel ignores an in-flight lookup and sends no mutation', async () => {
    let resolve!: (rows: typeof candidate[]) => void;
    const { api } = fixture({ securityCandidates: vi.fn().mockImplementation(() => new Promise(done => { resolve = done; })) });
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    await act(async () => resolve([candidate]));
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(api.linkWatchlist).not.toHaveBeenCalled();
  });

  it('failed confirmation preserves the item and requires selecting again', async () => {
    const { onLinked } = fixture({ linkWatchlist: vi.fn().mockRejectedValue(new ApiError(409)) });
    fireEvent.click(await screen.findByRole('radio'));
    fireEvent.click(screen.getByRole('button', { name: '같은 종목임을 확인하고 연결' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('기존 등록은 유지됩니다');
    expect(onLinked).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '같은 종목임을 확인하고 연결' })).toBeDisabled();
  });

  it('unavailable candidates cannot be selected', async () => {
    fixture({ securityCandidates: vi.fn().mockResolvedValue([{ ...candidate, selectable: false }]) });
    expect(await screen.findByRole('radio')).toBeDisabled();
  });
});
