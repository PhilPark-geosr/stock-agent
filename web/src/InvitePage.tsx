import { useState } from 'react';
import { ApiError, type Session, type WebApi } from './api';

interface InvitePageProps {
  api: WebApi;
  session: Session;
  onRedeemed: (session: Session) => void;
  onLogout: () => void | Promise<void>;
  onSessionExpired: () => void;
}

export function InvitePage({ api, session, onRedeemed, onLogout, onSessionExpired }: InvitePageProps) {
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function redeem(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !code.trim()) return;
    setPending(true);
    setMessage(null);
    try {
      onRedeemed(await api.redeem(code.trim()));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        onSessionExpired();
        return;
      }
      setMessage(error instanceof ApiError && error.status === 400
        ? '초대 코드를 확인해 주세요. 만료되었거나 이미 사용된 코드일 수 있습니다.'
        : '초대 코드 등록에 실패했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="center-shell">
      <section className="state-card invite-card" aria-labelledby="invite-title">
        <p className="eyebrow">PRIVATE BETA ACCESS</p>
        <h1 id="invite-title">초대 코드를 등록하세요</h1>
        <p className="lead">베타 이용 권한이 있는 초대 코드를 등록하면 관심 종목과 저장된 분석 결과를 볼 수 있습니다.</p>
        <div className="identity-row"><span>내 계정 ID</span><strong>{session.id}</strong></div>
        <form onSubmit={redeem} className="invite-form">
          <label htmlFor="invite-code">초대 코드</label>
          <input id="invite-code" value={code} onChange={event => setCode(event.target.value)} autoComplete="off" required />
          {message && <p className="notice error" role="alert">{message}</p>}
          <button className="primary-button wide" type="submit" disabled={pending}>
            {pending ? '등록 중…' : '초대 코드 등록'}
          </button>
        </form>
        <button className="text-button" type="button" onClick={onLogout}>로그아웃</button>
      </section>
    </main>
  );
}
