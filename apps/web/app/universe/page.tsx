"use client";

import {
  Check,
  Database,
  ListPlus,
  LoaderCircle,
  Plus,
  Search,
  Trash2
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";


const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

type ApiResponse<T> = {
  data: T;
  meta?: Record<string, unknown>;
};

type ProviderSymbol = {
  provider: string;
  symbol: string;
  is_primary: boolean;
  is_active: boolean;
};

type Instrument = {
  id: number;
  canonical_symbol: string;
  market: string;
  exchange: string;
  security_type: string;
  name_zh: string | null;
  name_en: string | null;
  currency: string | null;
  provider_symbols: ProviderSymbol[];
};

type Watchlist = {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  is_default: boolean;
  item_count: number;
};

type TrackingTier = "catalog" | "quote" | "daily" | "intraday";

type WatchlistItem = {
  id: number;
  watchlist_id: number;
  instrument_id: number;
  tracking_tier: TrackingTier;
  canonical_symbol: string;
  market: string;
  exchange: string;
  security_type: string;
  name_zh: string | null;
  name_en: string | null;
  quote_symbol: string | null;
};

type UniverseStats = {
  catalog: Array<{ market: string; security_type: string; count: number }>;
  tracking_tiers: Record<string, number>;
  storage: {
    catalog_bytes: number;
    ohlcv_bytes: number;
    projected_tracked_rows: number;
    projected_bytes_conservative: number;
  };
};

const tierLabels: Record<TrackingTier, string> = {
  catalog: "只存主檔",
  quote: "最新報價",
  daily: "日線資料",
  intraday: "盤中資料"
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    ...init
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export default function UniversePage() {
  const [market, setMarket] = useState<"TW" | "US">("TW");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Instrument[]>([]);
  const [total, setTotal] = useState(0);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState<number | null>(null);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [tier, setTier] = useState<TrackingTier>("quote");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busyInstrumentId, setBusyInstrumentId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newListName, setNewListName] = useState("");
  const [creatingList, setCreatingList] = useState(false);
  const [stats, setStats] = useState<UniverseStats | null>(null);

  const existingInstrumentIds = useMemo(
    () => new Set(items.map((item) => item.instrument_id)),
    [items]
  );

  const loadWatchlists = useCallback(async () => {
    const response = await requestJson<ApiResponse<Watchlist[]>>("/api/v1/watchlists");
    setWatchlists(response.data);
    setSelectedWatchlistId((current) => (
      current ?? response.data.find((item) => item.is_default)?.id ?? response.data[0]?.id ?? null
    ));
  }, []);

  const loadItems = useCallback(async (watchlistId: number) => {
    const response = await requestJson<ApiResponse<WatchlistItem[]>>(
      `/api/v1/watchlists/${watchlistId}/items`
    );
    setItems(response.data);
  }, []);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    loadWatchlists()
      .catch((reason) => {
        if (mounted) setError(reason instanceof Error ? reason.message : "清單載入失敗");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [loadWatchlists]);

  useEffect(() => {
    requestJson<ApiResponse<UniverseStats>>("/api/v1/instruments/stats")
      .then((response) => setStats(response.data))
      .catch(() => setStats(null));
  }, []);

  useEffect(() => {
    if (selectedWatchlistId === null) {
      setItems([]);
      return;
    }
    loadItems(selectedWatchlistId).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "清單內容載入失敗");
    });
  }, [loadItems, selectedWatchlistId]);

  useEffect(() => {
    let mounted = true;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setError(null);
      const params = new URLSearchParams({
        market,
        limit: "50",
        offset: "0"
      });
      if (query.trim()) params.set("q", query.trim());
      try {
        const response = await requestJson<ApiResponse<Instrument[]>>(
          `/api/v1/instruments?${params.toString()}`
        );
        if (!mounted) return;
        setResults(response.data);
        setTotal(Number(response.meta?.total ?? response.data.length));
      } catch (reason) {
        if (mounted) {
          setResults([]);
          setError(reason instanceof Error ? reason.message : "股票庫查詢失敗");
        }
      } finally {
        if (mounted) setSearching(false);
      }
    }, 250);
    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, [market, query]);

  async function addInstrument(instrument: Instrument) {
    if (selectedWatchlistId === null) return;
    setBusyInstrumentId(instrument.id);
    setError(null);
    try {
      await requestJson(`/api/v1/watchlists/${selectedWatchlistId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instrument_id: instrument.id,
          tracking_tier: tier
        })
      });
      await Promise.all([loadItems(selectedWatchlistId), loadWatchlists()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加入清單失敗");
    } finally {
      setBusyInstrumentId(null);
    }
  }

  async function removeItem(item: WatchlistItem) {
    if (selectedWatchlistId === null) return;
    setBusyInstrumentId(item.instrument_id);
    setError(null);
    try {
      await requestJson(`/api/v1/watchlists/${selectedWatchlistId}/items/${item.id}`, {
        method: "DELETE"
      });
      await Promise.all([loadItems(selectedWatchlistId), loadWatchlists()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "移除標的失敗");
    } finally {
      setBusyInstrumentId(null);
    }
  }

  async function createWatchlist() {
    if (!newListName.trim()) return;
    setCreatingList(true);
    setError(null);
    try {
      const response = await requestJson<ApiResponse<Watchlist>>("/api/v1/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newListName.trim() })
      });
      setNewListName("");
      await loadWatchlists();
      setSelectedWatchlistId(response.data.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建立清單失敗");
    } finally {
      setCreatingList(false);
    }
  }

  return (
    <main className="universe-page">
      <header className="universe-heading">
        <div>
          <span className="section-kicker">INSTRUMENT UNIVERSE</span>
          <h1>股票庫與自訂清單</h1>
          <p>搜尋全市場主檔，只有加入清單的標的才依追蹤層級取得行情資料。</p>
        </div>
        <div className="universe-count">
          <Database size={18} />
          <strong>{total.toLocaleString()}</strong>
          <span>{market} 標的</span>
        </div>
      </header>

      {error ? <div className="universe-error">{error}</div> : null}

      <section className="universe-toolbar" aria-label="股票庫篩選">
        <div className="universe-market-tabs" role="group" aria-label="市場">
          <button
            className={market === "TW" ? "active" : ""}
            onClick={() => setMarket("TW")}
            type="button"
          >
            台股
          </button>
          <button
            className={market === "US" ? "active" : ""}
            onClick={() => setMarket("US")}
            type="button"
          >
            美股
          </button>
        </div>
        <label className="universe-search">
          <Search size={17} />
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder={market === "TW" ? "搜尋代號、中文或英文名稱" : "搜尋 ticker 或公司名稱"}
            value={query}
          />
          {searching ? <LoaderCircle className="spin" size={16} /> : null}
        </label>
        <label className="universe-tier">
          <span>加入後追蹤</span>
          <select onChange={(event) => setTier(event.target.value as TrackingTier)} value={tier}>
            {Object.entries(tierLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
      </section>

      {stats ? (
        <section className="universe-capacity" aria-label="資料容量摘要">
          <span>
            Catalog
            <strong>{stats.catalog.reduce((sum, item) => sum + item.count, 0).toLocaleString()}</strong>
          </span>
          <span>
            已追蹤
            <strong>{Object.values(stats.tracking_tiers).reduce((sum, count) => sum + count, 0).toLocaleString()}</strong>
          </span>
          <span>
            目前資料庫
            <strong>{formatBytes(stats.storage.catalog_bytes + stats.storage.ohlcv_bytes)}</strong>
          </span>
          <span>
            追蹤層級估算
            <strong>{formatBytes(stats.storage.projected_bytes_conservative)}</strong>
          </span>
        </section>
      ) : null}

      <div className="universe-layout">
        <section className="universe-results" aria-labelledby="universe-results-title">
          <div className="universe-section-title">
            <div>
              <span>CATALOG</span>
              <h2 id="universe-results-title">搜尋結果</h2>
            </div>
            <small>顯示前 50 筆</small>
          </div>
          <div className="universe-table-wrap">
            <table className="universe-table">
              <thead>
                <tr>
                  <th>代號</th>
                  <th>名稱</th>
                  <th>交易所</th>
                  <th>類型</th>
                  <th aria-label="加入清單" />
                </tr>
              </thead>
              <tbody>
                {results.map((instrument) => {
                  const added = existingInstrumentIds.has(instrument.id);
                  return (
                    <tr key={instrument.id}>
                      <td>
                        <strong>{instrument.canonical_symbol}</strong>
                        <small>{instrument.provider_symbols.find((item) => item.provider === "yfinance")?.symbol}</small>
                      </td>
                      <td>
                        <strong>{instrument.name_zh ?? instrument.name_en ?? "—"}</strong>
                        {instrument.name_zh && instrument.name_en ? <small>{instrument.name_en}</small> : null}
                      </td>
                      <td>{instrument.exchange}</td>
                      <td><span className="universe-type-badge">{instrument.security_type}</span></td>
                      <td>
                        <button
                          aria-label={added ? `${instrument.canonical_symbol} 已在清單` : `加入 ${instrument.canonical_symbol}`}
                          className={`universe-row-action ${added ? "added" : ""}`}
                          disabled={added || selectedWatchlistId === null || busyInstrumentId === instrument.id}
                          onClick={() => addInstrument(instrument)}
                          title={added ? "已在目前清單" : "加入目前清單"}
                          type="button"
                        >
                          {busyInstrumentId === instrument.id
                            ? <LoaderCircle className="spin" size={16} />
                            : added ? <Check size={16} /> : <Plus size={16} />}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!searching && results.length === 0 ? (
              <div className="universe-empty">目前沒有符合條件的標的。</div>
            ) : null}
          </div>
        </section>

        <aside className="universe-lists" aria-labelledby="universe-list-title">
          <div className="universe-section-title">
            <div>
              <span>WATCHLIST</span>
              <h2 id="universe-list-title">自訂清單</h2>
            </div>
            <small>{items.length} 檔</small>
          </div>
          <select
            className="universe-list-select"
            disabled={loading || watchlists.length === 0}
            onChange={(event) => setSelectedWatchlistId(Number(event.target.value))}
            value={selectedWatchlistId ?? ""}
          >
            {watchlists.map((watchlist) => (
              <option key={watchlist.id} value={watchlist.id}>
                {watchlist.name} ({watchlist.item_count})
              </option>
            ))}
          </select>
          <div className="universe-create-list">
            <input
              aria-label="新清單名稱"
              onChange={(event) => setNewListName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") createWatchlist();
              }}
              placeholder="建立新清單"
              value={newListName}
            />
            <button
              aria-label="建立清單"
              disabled={creatingList || !newListName.trim()}
              onClick={createWatchlist}
              title="建立清單"
              type="button"
            >
              {creatingList ? <LoaderCircle className="spin" size={16} /> : <ListPlus size={16} />}
            </button>
          </div>
          <div className="universe-list-items">
            {items.map((item) => (
              <div className="universe-list-item" key={item.id}>
                <div>
                  <strong>{item.canonical_symbol}</strong>
                  <span>{item.name_zh ?? item.name_en ?? item.quote_symbol ?? "—"}</span>
                  <small>{tierLabels[item.tracking_tier]}</small>
                </div>
                <button
                  aria-label={`移除 ${item.canonical_symbol}`}
                  disabled={busyInstrumentId === item.instrument_id}
                  onClick={() => removeItem(item)}
                  title="從清單移除"
                  type="button"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
            {!loading && items.length === 0 ? (
              <div className="universe-empty compact">從左側搜尋結果加入標的。</div>
            ) : null}
          </div>
        </aside>
      </div>
    </main>
  );
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 MB";
  const megabytes = value / 1024 / 1024;
  if (megabytes < 1024) return `${megabytes.toFixed(megabytes < 10 ? 1 : 0)} MB`;
  return `${(megabytes / 1024).toFixed(1)} GB`;
}
