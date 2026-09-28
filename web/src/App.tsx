import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { AdminPage } from './AdminPage';
import { BetaAppPage } from './BetaAppPage';
import { InvitePage } from './InvitePage';
import { ApiError, type Session, type WebApi } from './api';

type SessionState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; session: Session }
  | { status: 'error'; message: string };

interface AppProps { api: WebApi; }

function Header({ session }: { session: Session | null }) {
  return (
    <header className="site-header">
      <Link className="brand" to={session?.has_beta_access ? '/app' : '/login'} aria-label="Stock Agent 홈">
        <span className="brand-mark" aria-hidden="true">S</span>
        <span><strong>Stock Agent</strong><small>PRIVATE BETA</small></span>
      </Link>
      <div className="header-actions">
        {session?.has_beta_access && <Link to="/app">서비스</Link>}
        {session && !session.has_beta_access && <Link to="/invite">초대 코드</Link>}
        {session?.is_operator && <Link to="/admin">초대 발급</Link>}
        <span className="secure-label"><i aria-hidden="true" /> 비공개 베타</span>
      </div>
    </header>
  );
}

function LoginPage({ api, onLogin }: { api: WebApi; onLogin: (session: Session) => void }) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function login() {
    if (pending) return;
    const nextController = new AbortController();
    controller.current = nextController;
    setPending(true);
    setMessage(null);
    try { onLogin(await api.login(nextController.signal)); }
    catch (error) {
      if (!nextController.signal.aborted) setMessage(error instanceof Error ? error.message : '로그인에 실패했습니다. 다시 시도해 주세요.');
    } finally { if (!nextController.signal.aborted) setPending(false); }
  }

  return <main className="login-shell"><section className="login-card" aria-labelledby="login-title">
    <p className="eyebrow">PRIVATE BETA</p><h1 id="login-title">Stock Agent<br />베타 서비스</h1>
    <p className="lead">카카오 계정으로 로그인한 뒤 초대 코드를 등록해 서비스 이용 권한을 받으세요.</p>
    {message && <p className="notice error" role="alert">{message}</p>}
    <button className="kakao-button" type="button" onClick={login} disabled={pending}><span aria-hidden="true">K</span>{pending ? '로그인 확인 중…' : '카카오로 로그인'}</button>
    <p className="privacy-note">로그인 후 내 계정 ID를 확인할 수 있습니다.</p>
  </section><aside className="login-aside" aria-label="서비스 안내"><p>STOCK AGENT</p><blockquote>초대받은 사용자에게<br />저장된 분석 결과를 제공합니다.</blockquote><span>PRIVATE BETA · Seoul</span></aside></main>;
}

export function App({ api }: AppProps) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    api.session().then(
      session => { if (active) setState({ status: 'authenticated', session }); },
      error => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) setState({ status: 'anonymous' });
        else setState({ status: 'error', message: '세션을 확인하지 못했습니다. 연결을 확인한 뒤 새로고침해 주세요.' });
      },
    );
    return () => { active = false; };
  }, [api]);

  async function logout() {
    setLogoutError(null);
    try {
      await api.logout();
      setState({ status: 'anonymous' });
      navigate('/login', { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState({ status: 'anonymous' });
        navigate('/login', { replace: true });
        return;
      }
      setLogoutError('로그아웃에 실패했습니다. 다시 시도해 주세요.');
    }
  }

  function sessionExpired() {
    setState({ status: 'anonymous' });
    navigate('/login', { replace: true });
  }

  let content;
  if (state.status === 'loading') content = <main className="center-shell"><p className="loading" role="status">세션을 확인하는 중…</p></main>;
  else if (state.status === 'error') content = <main className="center-shell"><section className="state-card"><h1>연결을 확인해 주세요</h1><p className="notice error" role="alert">{state.message}</p></section></main>;
  else if (state.status === 'anonymous') content = <Routes><Route path="/login" element={<LoginPage api={api} onLogin={session => setState({ status: 'authenticated', session })} />} /><Route path="*" element={<Navigate replace to="/login" />} /></Routes>;
  else {
    const { session } = state;
    const defaultPath = session.has_beta_access ? '/app' : '/invite';
    content = <Routes>
      <Route path="/login" element={<Navigate replace to={defaultPath} />} />
      <Route path="/invite" element={session.has_beta_access ? <Navigate replace to="/app" /> : <InvitePage api={api} session={session} onRedeemed={next => setState({ status: 'authenticated', session: next })} onLogout={logout} onSessionExpired={sessionExpired} />} />
      <Route path="/app" element={session.has_beta_access ? <BetaAppPage api={api} session={session} onLogout={logout} onSessionExpired={sessionExpired} /> : <Navigate replace to="/invite" />} />
      <Route path="/admin" element={session.is_operator ? <AdminPage api={api} session={session} onLogout={logout} onSessionExpired={sessionExpired} /> : <Navigate replace to={defaultPath} />} />
      <Route path="*" element={<Navigate replace to={defaultPath} />} />
    </Routes>;
  }

  return <div className="app-frame"><Header session={state.status === 'authenticated' ? state.session : null} />{logoutError && <p className="global-error" role="alert">{logoutError}</p>}{content}</div>;
}
