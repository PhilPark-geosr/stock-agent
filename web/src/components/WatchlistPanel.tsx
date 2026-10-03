import { useState } from 'react';
import type { WatchlistItem } from '../api';

interface Props {
  items: WatchlistItem[];
  selectedSymbol: string | null;
  loading: boolean;
  adding: boolean;
  removing: string | null;
  onAdd: (symbol: string) => Promise<boolean>;
  onSelect: (symbol: string) => void;
  onRemove: (item: WatchlistItem) => void;
}

export function WatchlistPanel({ items, selectedSymbol, loading, adding, removing, onAdd, onSelect, onRemove }: Props) {
  const [symbol, setSymbol] = useState('');
  const [search, setSearch] = useState('');
  const query = search.trim().toUpperCase();
  const visible = query ? items.filter(item => item.symbol.includes(query)) : items;

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const raw = symbol.trim().toUpperCase();
    if (!raw) return;
    if (await onAdd(raw.includes('.') ? raw : `${raw}.KS`)) setSymbol('');
  }

  return <section className="watchlist-panel" aria-labelledby="watchlist-title">
    <div className="panel-heading"><div><p className="step-label">WATCHLIST</p><h2 id="watchlist-title">관심 종목</h2></div><span>{items.length}개</span></div>
    <form className="symbol-form" onSubmit={add}>
      <label htmlFor="symbol">관심 종목 코드</label>
      <input id="symbol" value={symbol} onChange={event => setSymbol(event.target.value)} placeholder="예: 005930.KS" autoCapitalize="characters" required />
      <button className="primary-button" type="submit" disabled={adding || loading}>{adding ? '추가 중…' : '종목 추가'}</button>
    </form>
    <label className="search-label" htmlFor="watchlist-search">관심 종목 검색</label>
    <input id="watchlist-search" className="watchlist-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="내 관심 종목에서 코드 검색" />
    {loading ? <p className="loading" role="status">관심 종목을 불러오는 중…</p> : items.length === 0 ? <p className="empty-state">등록된 관심 종목이 없습니다. 종목 코드를 입력해 추가하세요.</p> : visible.length === 0 ? <p className="empty-state">일치하는 관심 종목이 없습니다.</p> :
      <ul className="watchlist" aria-label="관심 종목 목록">{visible.map(item => <li key={item.id} className={selectedSymbol === item.symbol ? 'selected' : ''}>
        <button className="watch-symbol" type="button" onClick={() => onSelect(item.symbol)} aria-label={`${item.symbol} 선택`}>{item.symbol}</button>
        <button className="remove-button" type="button" onClick={() => onRemove(item)} disabled={removing === item.symbol} aria-label={`${item.symbol} 삭제`}>삭제</button>
      </li>)}</ul>}
  </section>;
}
