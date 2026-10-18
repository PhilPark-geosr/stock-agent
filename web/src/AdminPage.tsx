import { useState } from 'react';
import { ApiError, type Invitation, type Session, type WebApi } from './api';

interface AdminPageProps {
  api: WebApi;
  session: Session;
  onLogout: () => void | Promise<void>;
  onSessionExpired: () => void;
  copyText?: (text: string) => Promise<void>;
}

function koreanExpiry(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Seoul',
  }).format(new Date(value));
}

export function AdminPage({
  api,
  session,
  onLogout,
  onSessionExpired,
  copyText = text => navigator.clipboard.writeText(text),
}: AdminPageProps) {
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  async function issue() {
    if (issuing) return;
    setIssuing(true);
    setMessage(null);
    setCopyMessage(null);
    try {
      setInvitation(await api.issue());
    } catch (error) {
      setInvitation(null);
      if (error instanceof ApiError && error.status === 401) {
        onSessionExpired();
        return;
      }
      setMessage(error instanceof ApiError && error.status === 403
        ? '운영자 권한을 확인할 수 없습니다.'
        : '초대 코드 발급 결과를 확인하지 못했습니다. 발급 내역을 확인한 뒤 다시 시도해 주세요.');
    } finally {
      setIssuing(false);
    }
  }

  async function copyCode() {
    if (!invitation) return;
    setCopyMessage(null);
    try {
      await copyText(invitation.code);
      setCopyMessage('코드를 복사했습니다.');
    } catch {
      setCopyMessage('코드를 복사하지 못했습니다. 직접 선택해 복사해 주세요.');
    }
  }

  return (
    <main className="page-shell">
      <section className="admin-intro" aria-labelledby="admin-title">
        <div>
          <p className="eyebrow">PRIVATE BETA · OPERATOR</p>
          <h1 id="admin-title">초대 코드 발급</h1>
          <p className="lead">7일 동안 사용할 수 있는 비공개 베타 초대 코드를 한 번에 하나씩 발급합니다.</p>
        </div>
        <div className="account-card" aria-label="현재 계정">
          <span>현재 계정</span>
          <strong>{session.id}</strong>
          <button className="text-button" type="button" onClick={onLogout}>로그아웃</button>
        </div>
      </section>

      <section className="issue-panel" aria-labelledby="issue-heading">
        <div className="issue-heading">
          <div>
            <p className="step-label">INVITATION</p>
            <h2 id="issue-heading">새 초대</h2>
          </div>
          <button className="primary-button" type="button" onClick={issue} disabled={issuing}>
            {issuing ? '발급 중…' : '초대 코드 발급'}
          </button>
        </div>

        {message && <p className="notice error" role="alert">{message}</p>}

        {invitation ? (
          <div className="invitation-result" aria-live="polite">
            <p className="result-label">발급된 코드</p>
            <code data-testid="invitation-code">{invitation.code}</code>
            <div className="result-footer">
              <p>만료 · 한국 시간 {koreanExpiry(invitation.expires_at)}</p>
              <button className="secondary-button" type="button" onClick={copyCode}>코드 복사</button>
            </div>
            {copyMessage && <p className="copy-status" role="status">{copyMessage}</p>}
          </div>
        ) : (
          <div className="empty-result">
            <span aria-hidden="true">＋</span>
            <p>발급 후 이곳에 코드와 만료 시간이 표시됩니다.</p>
          </div>
        )}
      </section>
    </main>
  );
}
