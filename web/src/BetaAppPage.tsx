import { useEffect, useRef, useState } from 'react';
import { ApiError, type AnalysisHistoryItem, type AnalysisResult, type Session, type WatchlistItem, type WebApi } from './api';

interface BetaAppPageProps {
  api: WebApi;
  session: Session;
  onLogout: () => void | Promise<void>;
  onSessionExpired: () => void;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(value));
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status === 403) return '현재 계정에는 베타 이용 권한이 없습니다.';
  return fallback;
}

export function BetaAppPage({ api, session, onLogout, onSessionExpired }: BetaAppPageProps) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState('');
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([]);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [detail, setDetail] = useState<AnalysisResult | null>(null);
  const [detailLoading, setDetailLoading] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const selectedSymbolRef = useRef<string | null>(null);

  useEffect(() => { selectedSymbolRef.current = selectedSymbol; }, [selectedSymbol]);

  function handleError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) {
      onSessionExpired();
      return;
    }
    setMessage(errorMessage(error, fallback));
  }

  useEffect(() => {
    let active = true;
    api.watchlist().then(
      rows => {
        if (!active) return;
        setItems(rows);
        setSelectedSymbol(rows[0]?.symbol ?? null);
      },
      error => { if (active) handleError(error, '관심 종목을 불러오지 못했습니다.'); },
    ).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api]);

  useEffect(() => {
    if (!selectedSymbol) {
      setHistory([]);
      setHasMoreHistory(false);
      setDetail(null);
      return;
    }
    let active = true;
    setHistoryLoading(true);
    setHistory([]);
    setHasMoreHistory(false);
    setDetail(null);
    setMessage(null);
    api.analysisHistory(selectedSymbol).then(
      rows => { if (active) { setHistory(rows); setHasMoreHistory(rows.length === 20); } },
      error => { if (active) handleError(error, '저장된 분석 이력을 불러오지 못했습니다.'); },
    ).finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [api, selectedSymbol]);

  async function loadMoreHistory() {
    if (!selectedSymbol || historyLoading) return;
    const target = selectedSymbol;
    setHistoryLoading(true);
    try {
      const rows = await api.analysisHistory(target, history.length);
      if (selectedSymbolRef.current === target) {
        setHistory(current => [...current, ...rows]);
        setHasMoreHistory(rows.length === 20);
      }
    } catch (error) {
      if (selectedSymbolRef.current === target) handleError(error, '저장된 분석 이력을 불러오지 못했습니다.');
    } finally {
      if (selectedSymbolRef.current === target) setHistoryLoading(false);
    }
  }

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!symbol.trim() || adding) return;
    setAdding(true);
    setMessage(null);
    try {
      const added = await api.addWatchlist(symbol.trim());
      setItems(current => current.some(item => item.id === added.id) ? current : [...current, added]);
      setSelectedSymbol(added.symbol);
      setSymbol('');
    } catch (error) {
      handleError(error, '관심 종목을 추가하지 못했습니다.');
    } finally {
      setAdding(false);
    }
  }

  async function remove(item: WatchlistItem) {
    if (removing) return;
    setRemoving(item.symbol);
    setMessage(null);
    try {
      await api.removeWatchlist(item.symbol);
      setItems(current => current.filter(candidate => candidate.id !== item.id));
      if (selectedSymbolRef.current === item.symbol) {
        setSelectedSymbol(items.find(candidate => candidate.id !== item.id)?.symbol ?? null);
      }
    } catch (error) {
      handleError(error, '관심 종목을 삭제하지 못했습니다.');
    } finally {
      setRemoving(null);
    }
  }

  async function showDetail(item: AnalysisHistoryItem) {
    if (!selectedSymbol || detailLoading !== null) return;
    setDetailLoading(item.id);
    setMessage(null);
    const target = selectedSymbol;
    try {
      const result = await api.analysisDetail(target, item.id);
      if (selectedSymbolRef.current === target) setDetail(result);
    } catch (error) {
      if (selectedSymbolRef.current === target) handleError(error, '분석 상세 결과를 불러오지 못했습니다.');
    } finally {
      setDetailLoading(null);
    }
  }

  return (
    <main className="page-shell beta-page">
      <section className="service-intro" aria-labelledby="service-title">
        <div>
          <p className="eyebrow">PRIVATE BETA</p>
          <h1 id="service-title">내 관심 종목</h1>
          <p className="lead">관심 종목의 공통 분석 이력과 주요 근거를 확인하세요.</p>
        </div>
        <div className="account-card"><span>내 계정</span><strong>{session.id}</strong><button className="text-button" type="button" onClick={onLogout}>로그아웃</button></div>
      </section>

      {message && <p className="notice error" role="alert">{message}</p>}
      <section className="watchlist-panel" aria-labelledby="watchlist-title">
        <div className="panel-heading"><div><p className="step-label">WATCHLIST</p><h2 id="watchlist-title">관심 종목</h2></div></div>
        <form className="symbol-form" onSubmit={add}>
          <label htmlFor="symbol">종목 코드</label>
          <input id="symbol" value={symbol} onChange={event => setSymbol(event.target.value)} placeholder="예: 005930.KS" autoCapitalize="characters" required />
          <button className="primary-button" type="submit" disabled={adding}>{adding ? '추가 중…' : '종목 추가'}</button>
        </form>
        {loading ? <p className="loading" role="status">관심 종목을 불러오는 중…</p> : items.length === 0 ? <p className="empty-state">등록한 관심 종목이 없습니다. 종목 코드를 입력해 추가하세요.</p> : (
          <ul className="watchlist" aria-label="관심 종목 목록">
            {items.map(item => <li key={item.id} className={selectedSymbol === item.symbol ? 'selected' : ''}>
              <button className="watch-symbol" type="button" onClick={() => setSelectedSymbol(item.symbol)} aria-label={`${item.symbol} 분석 이력`}>{item.symbol}</button>
              <button className="remove-button" type="button" onClick={() => remove(item)} disabled={removing === item.symbol} aria-label={`${item.symbol} 삭제`}>삭제</button>
            </li>)}
          </ul>
        )}
      </section>

      <section className="history-panel" aria-labelledby="history-title">
        <div><p className="step-label">SAVED ANALYSIS</p><h2 id="history-title">{selectedSymbol ? `${selectedSymbol} 분석 이력` : '분석 이력'}</h2></div>
        {!selectedSymbol ? <p className="empty-state">관심 종목을 선택하면 저장된 분석 이력을 볼 수 있습니다.</p> : historyLoading ? <p className="loading" role="status">분석 이력을 불러오는 중…</p> : history.length === 0 ? <p className="empty-state">저장된 분석 이력이 없습니다. 다음 예약 분석이 완료되면 여기에서 확인할 수 있습니다.</p> : (
          <ul className="history-list" aria-label={`${selectedSymbol} 저장된 분석 이력`}>
            {history.map(item => <li key={item.id}><button type="button" onClick={() => showDetail(item)} disabled={detailLoading !== null}><span>{formatDate(item.analyzed_at)}</span><strong>{item.overall_judgment}</strong><small>{item.summary}</small></button></li>)}
          </ul>
        )}
        {detailLoading !== null && <p className="loading" role="status">분석 상세 결과를 불러오는 중…</p>}
        {hasMoreHistory && <button className="secondary-button load-more" type="button" onClick={loadMoreHistory} disabled={historyLoading}>분석 이력 더 보기</button>}
        {detail && <article className="analysis-detail" aria-labelledby="detail-title"><p className="step-label">ANALYSIS DETAIL</p><h3 id="detail-title">{detail.symbol} · {detail.overall_judgment}</h3><p>{detail.summary}</p><h4>주요 근거</h4><ul>{detail.key_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul><h4>위험 요인</h4><ul>{detail.risk_factors.map(reason => <li key={reason}>{reason}</li>)}</ul>{detail.alert_reason && <p className="analysis-alert">알림: {detail.alert_reason}</p>}</article>}
      </section>
    </main>
  );
}
