import type { AnalysisHistoryItem, AnalysisResult } from '../api';

function formatDate(value: string | null): string {
  if (!value) return '정보 없음';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '정보 없음' : new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul',
  }).format(date);
}

function metric(value: unknown, suffix = ''): string {
  const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : NaN;
  return Number.isFinite(number) ? `${new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 }).format(number)}${suffix}` : '정보 없음';
}

interface AnalysisProps {
  symbol: string | null;
  detail: AnalysisResult | null;
  latestId: number | null;
  loading: boolean;
  running: boolean;
  onRun: () => void;
}

export function AnalysisPanel({ symbol, detail, latestId, loading, running, onRun }: AnalysisProps) {
  const levels = detail?.support_levels ?? {};
  return <section className="analysis-panel" aria-labelledby="analysis-title">
    <div className="panel-heading"><div><p className="step-label">SHARED ANALYSIS</p><h2 id="analysis-title">{symbol ? `${symbol} 공통 분석` : '공통 분석'}</h2></div>
      {symbol && <button className="primary-button" type="button" onClick={onRun} disabled={running || loading} aria-label="수동 분석 실행">{running ? '분석 실행 중…' : '수동 분석 실행'}</button>}</div>
    {!symbol ? <p className="empty-state">관심 종목을 선택하세요.</p> : loading && !detail ? <p className="loading" role="status">분석을 불러오는 중…</p> : !detail ? <p className="empty-state">저장된 분석이 없습니다. 수동 분석을 실행해 새 공통 결과를 만들 수 있습니다.</p> : <article className="analysis-detail">
      <p className="step-label">{detail.id === latestId ? 'LATEST ANALYSIS' : 'HISTORY DETAIL'} · {formatDate(detail.analyzed_at)}</p>
      <h3>{detail.symbol} · {detail.overall_judgment}</h3>
      <p>{detail.summary}</p>
      <dl className="analysis-metrics">
        <div><dt>분석 시점 종가</dt><dd>{metric(levels.latest_close, '원')}</dd></div>
        <div><dt>분석 시점 등락률</dt><dd>{metric(levels.change_percent, '%')}</dd></div>
        <div><dt>20일 평균 대비 거래량</dt><dd>{metric(levels.volume_ratio_20, '배')}</dd></div>
        <div><dt>20일 저가</dt><dd>{metric(levels.low_20, '원')}</dd></div>
        <div><dt>20일 고가</dt><dd>{metric(levels.high_20, '원')}</dd></div>
      </dl>
      <p className="analysis-time">시장 데이터 시각: {formatDate(detail.data_timestamp)}</p>
      <h4>주요 근거</h4><ul>{detail.key_reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul>
      <h4>위험 요인</h4><ul>{detail.risk_factors.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul>
      <div className="system-signal"><h4>공통 시장 신호</h4><p>{detail.should_alert ? detail.alert_reason || '신호 감지' : '감지된 신호 없음'}</p>
        {detail.triggered_alerts.length > 0 && <p>감지 조건: {detail.triggered_alerts.join(', ')}</p>}
        <small>이 표시는 내 조건 평가나 카카오 알림 발송 결과가 아닙니다.</small></div>
    </article>}
  </section>;
}

interface HistoryProps {
  symbol: string | null;
  items: AnalysisHistoryItem[];
  selectedId: number | null;
  loading: boolean;
  detailLoading: number | null;
  hasMore: boolean;
  onSelect: (item: AnalysisHistoryItem) => void;
  onLatest: () => void;
  onMore: () => void;
}

export function AnalysisHistoryPanel({ symbol, items, selectedId, loading, detailLoading, hasMore, onSelect, onLatest, onMore }: HistoryProps) {
  return <section className="history-panel" aria-labelledby="history-title">
    <div className="panel-heading"><div><p className="step-label">SAVED ANALYSIS</p><h2 id="history-title">{symbol ? `${symbol} 분석 이력` : '분석 이력'}</h2></div>
      {items.length > 0 && <button className="secondary-button" type="button" onClick={onLatest}>최신 분석 보기</button>}</div>
    {!symbol ? <p className="empty-state">관심 종목을 선택하면 분석 이력을 볼 수 있습니다.</p> : loading && items.length === 0 ? <p className="loading" role="status">분석 이력을 불러오는 중…</p> : items.length === 0 ? <p className="empty-state">저장된 분석 이력이 없습니다.</p> : <ul className="history-list" aria-label={`${symbol} 저장된 분석 이력`}>
      {items.map(item => <li key={item.id}><button type="button" onClick={() => onSelect(item)} aria-current={selectedId === item.id ? 'true' : undefined}>
        <span>#{item.id} · {formatDate(item.analyzed_at)}</span><strong>{item.overall_judgment}</strong><small>{item.summary}</small>
      </button></li>)}
    </ul>}
    {detailLoading !== null && <p className="loading" role="status">분석 상세를 불러오는 중…</p>}
    {hasMore && <button className="secondary-button load-more" type="button" onClick={onMore} disabled={loading}>분석 이력 더 보기</button>}
  </section>;
}
