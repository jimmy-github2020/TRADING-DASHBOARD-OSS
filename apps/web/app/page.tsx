"use client";

import { ChevronLeft, ChevronRight, LineChart, Plus, Search } from "lucide-react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type Time
} from "lightweight-charts";
import { KeyboardEvent, MouseEvent, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import watchlistConfig from "../config/watchlist.json";
import { useTheme } from "./theme-provider";

type ApiResponse<T> = {
  data: T;
  meta: Record<string, unknown>;
  timestamp: string;
};

type Health = {
  status: string;
  timestamp: string;
  db: string;
  redis: string;
};

type PortfolioHolding = {
  id: number;
  symbol: string;
  name_zh: string | null;
  name_en: string | null;
  category: string | null;
  owned: boolean;
};

type CatalogWatchlist = {
  id: number;
  is_default: boolean;
};

type CatalogWatchlistItem = {
  id: number;
  instrument_id: number;
  canonical_symbol: string;
  market: "TW" | "US" | string;
  security_type: string;
  name_zh: string | null;
  name_en: string | null;
  quote_symbol: string | null;
};

type DailyNote = {
  note_date: string;
  content: string;
  created_at: string | null;
  updated_at: string | null;
};

type BosScores = {
  profitability: number | null;
  growth: number | null;
  value: number | null;
  financial: number | null;
  momentum: number | null;
};

type MyScores = {
  profit: number | null;
  growth: number | null;
  value: number | null;
  finance: number | null;
  momentum: number | null;
};

type Fundamentals = {
  symbol: string;
  name: string;
  currency: string | null;
  pe: number | null;
  pb: number | null;
  roe: number | null;
  eps_ttm: number | null;
  dividend_yield: number | null;
  week_52_position: number | null;
  beta: number | null;
  market_cap: number | null;
  bos_scores?: BosScores | null;
};

type NoteStatus = "idle" | "loading" | "editing" | "saving" | "saved" | "failed";
type Timeframe = "5m" | "1h" | "1d";
type RangeValue = "1d" | "3d" | "1w" | "2w" | "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "5y" | "10y";
type MaKey = "ma5" | "ma10" | "ma20" | "ma60";
type IndicatorTab = "rsi" | "kd" | "macd";

type WatchlistConfigItem = {
  symbol: string;
  label: string;
};

type WatchlistConfigGroup = {
  id: string;
  label: string;
  region: "tw" | "us";
  items: WatchlistConfigItem[];
};

type WatchlistItem = {
  id: string;
  symbol: string;
  name_zh: string | null;
  name_en: string | null;
  category: string | null;
  region: "tw" | "us";
};

type MarketQuote = {
  symbol: string;
  provider: string | null;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  volume: number | null;
  candle_time: string | null;
  source: string;
};

type Candle = {
  time: string;
  symbol: string;
  timeframe: string;
  provider: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

type Indicators = {
  rsi_14: number | null;
  macd: {
    macd: number | null;
    signal: number | null;
    histogram: number | null;
  };
  bb_20_2: {
    middle: number | null;
    upper: number | null;
    lower: number | null;
  };
  kd_9_3: {
    k: number | null;
    d: number | null;
  };
  ema_20: number | null;
  atr_14: number | null;
  obv: number | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";
const timeframes = ["5m", "1h", "1d"] as const;
const rangeOptions: Record<Timeframe, Array<{ label: string; value: RangeValue }>> = {
  "1d": [
    { label: "1M", value: "1m" },
    { label: "3M", value: "3m" },
    { label: "6M", value: "6m" },
    { label: "1Y", value: "1y" },
    { label: "3Y", value: "3y" },
    { label: "5Y", value: "5y" },
    { label: "10Y", value: "10y" }
  ],
  "1h": [
    { label: "1W", value: "1w" },
    { label: "1M", value: "1m" },
    { label: "3M", value: "3m" },
    { label: "6M", value: "6m" },
    { label: "1Y", value: "1y" },
    { label: "2Y", value: "2y" }
  ],
  "5m": [
    { label: "1D", value: "1d" },
    { label: "3D", value: "3d" },
    { label: "1W", value: "1w" },
    { label: "2W", value: "2w" },
    { label: "1M", value: "1m" }
  ]
};
const defaultRangeByTimeframe: Record<Timeframe, RangeValue> = {
  "5m": "1d",
  "1h": "1m",
  "1d": "1y"
};
const maDefinitions: Array<{ key: MaKey; label: string; period: number; colorVar: string; fallback: string }> = [
  { key: "ma5", label: "MA5", period: 5, colorVar: "--chart-ma5", fallback: "#ffffff" },
  { key: "ma10", label: "MA10", period: 10, colorVar: "--chart-ma10", fallback: "#f5c518" },
  { key: "ma20", label: "MA20", period: 20, colorVar: "--chart-ma20", fallback: "#ff9d00" },
  { key: "ma60", label: "MA60", period: 60, colorVar: "--chart-ma60", fallback: "#4f98a3" }
];
const primaryIndexTiles = watchlistConfig.tickerBar.indices;
const commodityFxTiles = watchlistConfig.tickerBar.commodities;
const watchlistGroups = watchlistConfig.groups as WatchlistConfigGroup[];
const headlineTiles = [...primaryIndexTiles, ...commodityFxTiles];
const headlineSymbols = headlineTiles.map((item) => item.symbol);
const quotePollMs = 15000;

function readCssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function getChartColors() {
  return {
    background: readCssVar("--chart-bg", "#111827"),
    grid: readCssVar("--chart-grid", "#1f2937"),
    border: readCssVar("--chart-border", "#263244"),
    text: readCssVar("--chart-text", "#94a3b8"),
    up: readCssVar("--chart-up", "#00d4aa"),
    down: readCssVar("--chart-down", "#ef4444"),
    volumeUp: readCssVar("--chart-volume-up", "rgba(0, 212, 170, 0.22)"),
    volumeDown: readCssVar("--chart-volume-down", "rgba(239, 68, 68, 0.2)"),
    ma10: readCssVar("--chart-ma10", "#f5c518"),
    ma20: readCssVar("--chart-ma20", "#ff9d00"),
    ma60: readCssVar("--chart-ma60", "#4f98a3"),
    bbBand: readCssVar("--chart-bb-band", "#ffffff"),
    bbArea: readCssVar("--chart-bb-area", "rgba(255, 255, 255, 0.04)"),
    guideHot: readCssVar("--chart-guide-hot", "#a13544"),
    guideCool: readCssVar("--chart-guide-cool", "#6daa45"),
    zero: readCssVar("--chart-zero", "#64748b"),
    macdDif: readCssVar("--chart-macd-dif", "#ffffff")
  };
}

export default function Home() {
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([]);
  const [catalogWatchlistItems, setCatalogWatchlistItems] = useState<CatalogWatchlistItem[]>([]);
  const [marketQuotes, setMarketQuotes] = useState<MarketQuote[]>([]);
  const [headlineQuotes, setHeadlineQuotes] = useState<MarketQuote[]>([]);
  const [headlineLoading, setHeadlineLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(true);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [fundamentalsLoading, setFundamentalsLoading] = useState(false);
  const [fundamentalsError, setFundamentalsError] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState("2330.TW");
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [selectedRange, setSelectedRange] = useState<RangeValue>("1y");
  const [visibleMa, setVisibleMa] = useState<Record<MaKey, boolean>>({
    ma5: false,
    ma10: false,
    ma20: true,
    ma60: true
  });
  const [showBollinger, setShowBollinger] = useState(false);
  const [activeIndicator, setActiveIndicator] = useState<IndicatorTab>("rsi");
  const [chartWarning, setChartWarning] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [searchSymbol, setSearchSymbol] = useState("");
  const [searchQuote, setSearchQuote] = useState<MarketQuote | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState(false);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState<Record<"signals" | "fundamentals" | "scores" | "notes", boolean>>({
    signals: false,
    fundamentals: true,
    scores: false,
    notes: false
  });
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    "tw-stocks": true,
    "us-etf": true,
    "us-stocks": true
  });
  const [noteDate, setNoteDate] = useState("");
  const [dailyNote, setDailyNote] = useState("");
  const [noteStatus, setNoteStatus] = useState<NoteStatus>("idle");
  const [noteLoading, setNoteLoading] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const lastSavedNoteRef = useRef("");

  const selectedTicker = useMemo(
    () => headlineTiles.find((item) => item.symbol === selectedSymbol) ?? null,
    [selectedSymbol]
  );

  function selectSymbol(symbol: string) {
    setSelectedSymbol(symbol);
  }

  const selectWatchlistSymbol = selectSymbol;

  function selectTickerSymbol(symbol: string, label?: string) {
    selectSymbol(symbol);
  }

  const groupedWatchlist = useMemo(() => {
    const keyword = searchSymbol.trim().toLowerCase();

    function fromConfigItem(item: WatchlistConfigItem, group: WatchlistConfigGroup): WatchlistItem {
      const holding = holdings.find((candidate) => candidate.symbol === item.symbol);
      return {
        id: holding ? `holding-${holding.id}` : `config-${group.id}-${item.symbol}`,
        symbol: item.symbol,
        name_zh: holding?.name_zh ?? item.label,
        name_en: holding?.name_en ?? item.label,
        category: group.label,
        region: group.region
      };
    }

    return watchlistGroups.map((group) => {
      let items: WatchlistItem[];
      const catalogItems = catalogWatchlistItems
        .filter((item) => {
          const isEtf = item.security_type === "etf";
          if (group.id === "tw-etf") return item.market === "TW" && isEtf;
          if (group.id === "tw-stocks") return item.market === "TW" && !isEtf;
          if (group.id === "us-etf") return item.market === "US" && isEtf;
          if (group.id === "us-stocks") return item.market === "US" && !isEtf;
          return false;
        })
        .map((item) => ({
          id: `catalog-${item.id}`,
          symbol: item.quote_symbol ?? item.canonical_symbol,
          name_zh: item.name_zh,
          name_en: item.name_en,
          category: group.label,
          region: group.region
        }));
      if (group.id === "tw-etf" || group.id === "tw-stocks") {
        const domesticCategory = group.id === "tw-etf" ? "ETF" : "股票";
        const domesticItems = holdings
          .filter((item) => item.category === domesticCategory)
          .map((item) => ({
            id: `holding-${item.id}`,
            symbol: item.symbol,
            name_zh: item.name_zh,
            name_en: item.name_en,
            category: group.label,
            region: group.region
          }));
        items = domesticItems.length > 0 ? domesticItems : group.items.map((item) => fromConfigItem(item, group));
      } else {
        items = group.items.map((item) => fromConfigItem(item, group));
      }

      items = Array.from(
        new Map([...catalogItems, ...items].map((item) => [item.symbol, item])).values()
      );
      return {
        ...group,
        items: items.filter((item) => {
          if (headlineSymbols.includes(item.symbol)) return false;
          if (!keyword) return true;
          return (
            item.symbol.toLowerCase().includes(keyword) ||
            (item.name_zh ?? "").toLowerCase().includes(keyword) ||
            (item.name_en ?? "").toLowerCase().includes(keyword)
          );
        })
      };
    });
  }, [catalogWatchlistItems, holdings, searchSymbol]);

  const allWatchlistItems = useMemo(
    () => groupedWatchlist.flatMap((group) => group.items),
    [groupedWatchlist]
  );

  const selectedWatchlistItem = useMemo(
    () => allWatchlistItems.find((item) => item.symbol === selectedSymbol) ?? null,
    [allWatchlistItems, selectedSymbol]
  );

  const selectedQuote = useMemo(
    () =>
      marketQuotes.find((item) => item.symbol === selectedSymbol) ??
      headlineQuotes.find((item) => item.symbol === selectedSymbol) ??
      null,
    [headlineQuotes, marketQuotes, selectedSymbol]
  );

  const selectedDisplayName = selectedWatchlistItem?.name_zh ?? selectedTicker?.label ?? selectedSymbol;
  const selectedDetailName = selectedWatchlistItem?.name_en ?? selectedTicker?.label ?? "Market symbol";

  useEffect(() => {
    setNoteDate(todayInputDate());
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadHoldings() {
      setWatchlistLoading(true);
      try {
        const response = await fetchJson<ApiResponse<PortfolioHolding[]>>("/api/v1/portfolio/holdings");
        if (!mounted) return;
        setHoldings(response.data);
        let catalogItems: CatalogWatchlistItem[] = [];
        try {
          const lists = await fetchJson<ApiResponse<CatalogWatchlist[]>>("/api/v1/watchlists");
          const selectedList = lists.data.find((item) => item.is_default) ?? lists.data[0];
          if (selectedList) {
            const itemResponse = await fetchJson<ApiResponse<CatalogWatchlistItem[]>>(
              `/api/v1/watchlists/${selectedList.id}/items`
            );
            catalogItems = itemResponse.data;
            if (mounted) setCatalogWatchlistItems(catalogItems);
          }
        } catch {
          if (mounted) setCatalogWatchlistItems([]);
        }
        setSelectedSymbol((current) => (
          current
          || catalogItems[0]?.quote_symbol
          || catalogItems[0]?.canonical_symbol
          || response.data[0]?.symbol
          || "2330.TW"
        ));
      } catch (error) {
        if (mounted) setApiError(error instanceof Error ? error.message : "Portfolio load error");
      } finally {
        if (mounted) setWatchlistLoading(false);
      }
    }

    loadHoldings();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadHeadlineQuotes() {
      setHeadlineLoading(true);
      try {
        const response = await fetchQuotes(headlineSymbols);
        if (mounted) setHeadlineQuotes(response);
      } finally {
        if (mounted) setHeadlineLoading(false);
      }
    }

    loadHeadlineQuotes();
    const timer = window.setInterval(loadHeadlineQuotes, quotePollMs);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (allWatchlistItems.length === 0) return;
    let mounted = true;
    const symbols = Array.from(
      new Set(allWatchlistItems.map((item) => item.symbol).filter((symbol) => !headlineSymbols.includes(symbol)))
    );

    async function loadWatchlistQuotes() {
      try {
        const response = await fetchQuotes(symbols);
        if (mounted) setMarketQuotes(response);
      } catch {
        if (mounted) setMarketQuotes([]);
      }
    }

    loadWatchlistQuotes();
    const timer = window.setInterval(loadWatchlistQuotes, quotePollMs);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [allWatchlistItems]);

  useEffect(() => {
    if (!selectedSymbol) return;
    let mounted = true;
    const provider = providerForSymbol(selectedSymbol);

    async function loadMarketData() {
      const query = new URLSearchParams({
        symbol: selectedSymbol,
        provider,
        interval: timeframe,
        range: selectedRange,
        limit: limitForRange(timeframe, selectedRange).toString()
      });
      try {
        const response = await fetchJson<ApiResponse<Candle[]>>(`/api/ohlcv?${query.toString()}`);
        if (!mounted) return;
        setCandles(response.data);
        setIndicators(calculateLatestIndicators(response.data));
        setChartWarning(typeof response.meta.warning === "string" ? response.meta.warning : null);
        setApiError(null);
      } catch {
        if (!mounted) return;
        setCandles([]);
        setIndicators(null);
        setChartWarning(null);
        setApiError(null);
      }
    }

    loadMarketData();
    return () => {
      mounted = false;
    };
  }, [selectedSymbol, timeframe, selectedRange]);

  useEffect(() => {
    if (!selectedSymbol) return;
    let mounted = true;

    async function loadFundamentals() {
      setFundamentalsLoading(true);
      setFundamentalsError(null);
      try {
        const query = new URLSearchParams({ symbol: selectedSymbol });
        const response = await fetchJson<ApiResponse<Fundamentals>>(`/api/fundamentals?${query.toString()}`);
        if (!mounted) return;
        setFundamentals(response.data);
      } catch (error) {
        if (!mounted) return;
        setFundamentals(null);
        setFundamentalsError(error instanceof Error ? error.message : "Fundamentals load error");
      } finally {
        if (mounted) setFundamentalsLoading(false);
      }
    }

    loadFundamentals();
    return () => {
      mounted = false;
    };
  }, [selectedSymbol]);

  useEffect(() => {
    if (!noteDate) return;
    let mounted = true;

    async function loadDailyNote() {
      setNoteLoading(true);
      setNoteStatus("loading");
      setLastSavedAt(null);
      try {
        const response = await fetchJson<DailyNote>(`/api/notes/${noteDate}`);
        if (!mounted) return;
        const content = response.content ?? "";
        setDailyNote(content);
        lastSavedNoteRef.current = content;
        setLastSavedAt(response.updated_at);
        setNoteStatus(response.updated_at ? "saved" : "idle");
      } catch {
        if (!mounted) return;
        setDailyNote("");
        lastSavedNoteRef.current = "";
        setNoteStatus("failed");
      } finally {
        if (mounted) setNoteLoading(false);
      }
    }

    loadDailyNote();
    return () => {
      mounted = false;
    };
  }, [noteDate]);

  useEffect(() => {
    if (!noteDate) return;
    if (noteLoading || dailyNote === lastSavedNoteRef.current) return;

    const timer = window.setTimeout(async () => {
      setNoteStatus("saving");
      try {
        const response = await fetchJson<DailyNote>(`/api/notes/${noteDate}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: dailyNote })
        });
        lastSavedNoteRef.current = response.content;
        setLastSavedAt(response.updated_at);
        setNoteStatus("saved");
      } catch {
        setNoteStatus("failed");
        window.setTimeout(() => {
          setNoteStatus(lastSavedNoteRef.current === dailyNote ? "saved" : "editing");
        }, 3000);
      }
    }, 1500);

    return () => {
      window.clearTimeout(timer);
    };
  }, [dailyNote, noteDate, noteLoading]);

  async function lookupSymbol() {
    const symbol = normalizeSymbol(searchSymbol);
    setSearchError(null);
    setSearchQuote(null);
    if (!symbol) return;
    if (headlineSymbols.includes(symbol)) {
      setSearchError("此標的已在上方行情區塊顯示，避免重複加入 Watchlist。");
      return;
    }
    setSearching(true);
    try {
      const quote = (await fetchQuotes([symbol]))[0];
      if (!quote || quote.price === null) {
        setSearchError("查無報價，請確認代號格式，例如 2330.TW。");
        return;
      }
      setSearchQuote(quote);
    } catch {
      setSearchError("查詢失敗，請稍後再試。");
    } finally {
      setSearching(false);
    }
  }

  async function addSearchResult() {
    if (!searchQuote) return;
    setAdding(true);
    try {
      const response = await fetchJson<ApiResponse<PortfolioHolding>>("/api/v1/portfolio/holdings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: searchQuote.symbol,
          name_zh: searchQuote.symbol,
          name_en: searchQuote.symbol,
          category: "觀察",
          owned: false
        })
      });
      setHoldings((current) => {
        const withoutExisting = current.filter((item) => item.symbol !== response.data.symbol);
        return [...withoutExisting, response.data];
      });
      selectWatchlistSymbol(response.data.symbol);
      setSearchSymbol("");
      setSearchQuote(null);
      setSearchError(null);
    } finally {
      setAdding(false);
    }
  }

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      lookupSymbol();
    }
  }

  function updateDailyNote(value: string) {
    setDailyNote(value);
    if (!noteLoading) setNoteStatus("editing");
  }

  function shiftNoteDate(days: number) {
    setNoteDate((current) => addDaysToInputDate(current, days));
  }

  function changeTimeframe(next: Timeframe) {
    setTimeframe(next);
    setSelectedRange(defaultRangeByTimeframe[next]);
  }

  function toggleMa(key: MaKey) {
    setVisibleMa((current) => ({ ...current, [key]: !current[key] }));
  }

  function toggleRightPanel(panel: "signals" | "fundamentals" | "scores" | "notes") {
    setRightPanelCollapsed((current) => ({ ...current, [panel]: !current[panel] }));
  }

  return (
    <main className="dashboard-shell app-layout">
      {apiError ? <div className="error-banner">{apiError}</div> : null}

      <section className="headline-market-panel">
        <MarketTileSection
          title="主要指數"
          items={primaryIndexTiles}
          quotes={headlineQuotes}
          loading={headlineLoading}
          columns="eight"
          selectedSymbol={selectedSymbol}
          onSelectSymbol={selectTickerSymbol}
        />
        <MarketTileSection
          title="商品 / 匯率"
          items={commodityFxTiles}
          quotes={headlineQuotes}
          loading={headlineLoading}
          columns="six"
          selectedSymbol={selectedSymbol}
          onSelectSymbol={selectTickerSymbol}
        />
      </section>

      <section className={`dashboard-grid body-row ${leftCollapsed ? "left-collapsed" : ""} ${rightCollapsed ? "right-collapsed" : ""}`}>
        <aside className="watchlist-panel">
          <button className="collapse-button left-toggle" aria-label={leftCollapsed ? "Expand watchlist" : "Collapse watchlist"} onClick={() => setLeftCollapsed((value) => !value)}>
            {leftCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
          {leftCollapsed ? (
            <div className="collapsed-rail">
              <Search size={16} />
            </div>
          ) : (
            <>
          <PanelHeader title="Watchlist" value={`${allWatchlistItems.length} items`} />
          <a className="watchlist-manage-link" href="/universe">
            <span>管理股票庫與自訂清單</span>
            <ChevronRight size={14} />
          </a>
          <div className="watchlist-search">
            <div className="watchlist-search-row">
              <Search size={14} />
              <input
                value={searchSymbol}
                onChange={(event) => setSearchSymbol(event.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="輸入代號，如 2330.TW"
              />
              <button aria-label="Search symbol" disabled={searching} onClick={lookupSymbol} type="button">
                <Plus size={14} />
              </button>
            </div>
            {searchError ? <p className="watchlist-search-error">{searchError}</p> : null}
            {searchQuote ? (
              <div className="watchlist-search-result">
                <span>{searchQuote.symbol}</span>
                <strong>{formatNumber(searchQuote.price)}</strong>
                <em className={classForChange(searchQuote.change_pct)}>{formatPercent(searchQuote.change_pct)}</em>
                <button disabled={adding} onClick={addSearchResult} type="button">加入 Watchlist</button>
              </div>
            ) : null}
          </div>

          <div className="watchlist">
            {watchlistLoading ? (
              <WatchlistSkeleton />
            ) : (
              groupedWatchlist.map((group) => (
                <div className={`watchlist-group ${group.region === "us" ? "foreign-group" : ""}`} key={group.id}>
                  <button className={`watchlist-group-header ${group.region === "us" ? "foreign" : ""}`} onClick={() => setCollapsedGroups((current) => ({ ...current, [group.id]: !current[group.id] }))} type="button">
                    <span>{collapsedGroups[group.id] ? "▶" : "▼"} {group.label}</span>
                    <em>{group.items.length}</em>
                  </button>
                  {collapsedGroups[group.id] ? null : group.items.map((item) => {
                    const quote = marketQuotes.find((snapshot) => snapshot.symbol === item.symbol);
                    return (
                      <button
                        className={`watch-row ${item.symbol === selectedSymbol ? "active" : ""}`}
                        key={item.symbol}
                        onClick={() => selectWatchlistSymbol(item.symbol)}
                        title={item.name_en ?? item.symbol}
                      >
                        <div className="watch-name-line">
                          <strong>{item.name_zh ?? item.symbol}</strong>
                          <span>{item.symbol}</span>
                        </div>
                        <div className="watch-price-line">
                          <strong>{formatNumber(quote?.price)}</strong>
                          <span className={classForChange(quote?.change_pct)}>{formatPercent(quote?.change_pct)}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>
          <div className="watchlist-footer">v0.4 desktop layout</div>
            </>
          )}
        </aside>

        <section className="chart-panel">
          <div className="chart-toolbar">
            <div>
              <p className="panel-kicker">{providerForSymbol(selectedSymbol)}</p>
              <h1>{selectedDisplayName}</h1>
              <span>{selectedSymbol} · {selectedDetailName}</span>
            </div>
            <div className="chart-controls">
              <div className="overlay-control" aria-label="Chart overlays">
                {maDefinitions.map((item) => (
                  <button
                    className={visibleMa[item.key] ? "selected" : ""}
                    key={item.key}
                    onClick={() => toggleMa(item.key)}
                    type="button"
                  >
                    {item.label}
                  </button>
                ))}
                <button className={showBollinger ? "selected" : ""} onClick={() => setShowBollinger((value) => !value)} type="button">
                  BB
                </button>
              </div>
              <div className="timeframe-control" aria-label="Timeframe">
                {timeframes.map((item) => (
                  <button className={item === timeframe ? "selected" : ""} key={item} onClick={() => changeTimeframe(item)} type="button">
                    {timeframeLabel(item)}
                  </button>
                ))}
              </div>
              <div className="range-control" aria-label="Chart range">
                {rangeOptions[timeframe].map((item) => (
                  <button className={item.value === selectedRange ? "selected" : ""} key={item.value} onClick={() => setSelectedRange(item.value)} type="button">
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="summary-bar">
            <Metric label="Last" value={formatNumber(selectedQuote?.price)} />
            <Metric label="Change" value={formatNumber(selectedQuote?.change)} tone={selectedQuote?.change} />
            <Metric label="Change %" value={formatPercent(selectedQuote?.change_pct)} tone={selectedQuote?.change_pct} />
            <Metric label="Volume" value={selectedSymbol === "TWD=X" ? "—" : formatCompact(selectedQuote?.volume)} />
          </div>

          <MarketChart
            candles={candles}
            indicators={indicators}
            timeframe={timeframe}
            visibleMa={visibleMa}
            showBollinger={showBollinger}
            warning={chartWarning}
          />

          <div className="embedded-indicators">
            <IndicatorPanel
              activeIndicator={activeIndicator}
              candles={candles}
              indicators={indicators}
              onSelectIndicator={setActiveIndicator}
            />
          </div>
        </section>

        <aside className="right-panel">
          <button className="collapse-button right-toggle" aria-label={rightCollapsed ? "Expand right panel" : "Collapse right panel"} onClick={() => setRightCollapsed((value) => !value)}>
            {rightCollapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
          </button>
          {rightCollapsed ? (
            <div className="collapsed-rail">
              <LineChart size={16} />
            </div>
          ) : (
            <>
              <RightPanelSection
                collapsed={rightPanelCollapsed.signals}
                onToggle={() => toggleRightPanel("signals")}
                title="技術訊號"
                value={selectedSymbol}
              >
                <TechnicalSignals indicators={indicators} quote={selectedQuote} symbol={selectedSymbol} />
              </RightPanelSection>

              <RightPanelSection
                collapsed={rightPanelCollapsed.fundamentals}
                onToggle={() => toggleRightPanel("fundamentals")}
                title="個股評分 & 關鍵數據"
                value="T4-2"
              >
                <FundamentalsPanel
                  data={fundamentals}
                  displayName={selectedDisplayName}
                  error={fundamentalsError}
                  loading={fundamentalsLoading}
                  symbol={selectedSymbol}
                />
              </RightPanelSection>

              <RightPanelSection
                collapsed={rightPanelCollapsed.scores}
                onToggle={() => toggleRightPanel("scores")}
                title="我的評分"
                value={selectedSymbol}
              >
                <MyScorePanel symbol={selectedSymbol} />
              </RightPanelSection>

              <RightPanelSection
                collapsed={rightPanelCollapsed.notes}
                headerExtra={<strong className={`note-status ${noteStatus}`}>{noteStatusText(noteStatus, lastSavedAt)}</strong>}
                onToggle={() => toggleRightPanel("notes")}
                title="每日筆記"
                value={noteDate ? formatNoteDateLabel(noteDate) : ""}
              >
                <div className="daily-note-panel">
                  <div className="daily-note-date-row">
                    <button aria-label="前一天" onClick={() => shiftNoteDate(-1)} type="button">‹</button>
                    <input
                      aria-label="選擇筆記日期"
                      max="9999-12-31"
                      onChange={(event) => setNoteDate(event.target.value || todayInputDate())}
                      type="date"
                      value={noteDate}
                    />
                    <button aria-label="後一天" onClick={() => shiftNoteDate(1)} type="button">›</button>
                    <button onClick={() => setNoteDate(todayInputDate())} type="button">今天</button>
                  </div>
                  <textarea
                    disabled={noteLoading}
                    value={dailyNote}
                    onChange={(event) => updateDailyNote(event.target.value)}
                    placeholder="今日觀察、操作記錄…"
                  />
                </div>
              </RightPanelSection>
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

function MarketTileSection({
  title,
  items,
  quotes,
  loading,
  columns,
  selectedSymbol,
  onSelectSymbol
}: {
  title: string;
  items: Array<{ symbol: string; label: string }>;
  quotes: MarketQuote[];
  loading: boolean;
  columns: "six" | "eight";
  selectedSymbol: string;
  onSelectSymbol: (symbol: string, label?: string) => void;
}) {
  function handleSelect(event: MouseEvent<HTMLDivElement>) {
    const item = (event.target as HTMLElement).closest<HTMLElement>(".ticker-item");
    const symbol = item?.dataset.symbol;
    const label = item?.dataset.label;
    if (!symbol) return;
    console.log("Ticker clicked:", symbol, label);
    onSelectSymbol(symbol, label);
  }

  return (
    <section className="headline-market-section">
      <div className="section-title-row">
        <h2>{title}</h2>
        <span>{items.length} symbols</span>
      </div>
      <div className={`headline-market-grid ticker-scrollable ${columns}`} onClick={handleSelect}>
        {loading
          ? items.map((item) => <MarketTileSkeleton key={item.symbol} />)
          : items.map((item) => (
              <MarketTile
                active={item.symbol === selectedSymbol}
                key={item.symbol}
                label={item.label}
                quote={quotes.find((quote) => quote.symbol === item.symbol)}
                symbol={item.symbol}
              />
            ))}
      </div>
    </section>
  );
}

function MarketTile({
  active,
  label,
  symbol,
  quote
}: {
  active: boolean;
  label: string;
  symbol: string;
  quote: MarketQuote | undefined;
}) {
  const changeClass = classForChange(quote?.change_pct);
  const direction =
    quote?.change_pct === null || quote?.change_pct === undefined || Number.isNaN(quote.change_pct)
      ? ""
      : quote.change_pct > 0
        ? "▲ "
        : quote.change_pct < 0
          ? "▼ "
          : "";

  return (
    <button
      className={`headline-market-tile ticker-item ${active ? "ticker-active" : ""}`}
      data-label={label}
      data-symbol={symbol}
      title={symbol}
      type="button"
    >
      <div className="ticker-row-top">
        <span className="ticker-label">{label}</span>
        <span className="ticker-symbol">{symbol}</span>
      </div>
      <div className="ticker-row-bottom">
        <strong className="ticker-price">{formatNumber(quote?.price)}</strong>
        <p className={`ticker-change ${changeClass}`}>{direction}{formatPercent(quote?.change_pct)}</p>
      </div>
    </button>
  );
}

function MarketTileSkeleton() {
  return (
    <div className="headline-market-tile skeleton">
      <span />
      <strong />
      <p />
    </div>
  );
}

function WatchlistSkeleton() {
  return (
    <div className="watchlist-group">
      {Array.from({ length: 8 }).map((_, index) => (
        <div className="watch-row skeleton-watch" key={index}>
          <span />
          <strong />
        </div>
      ))}
    </div>
  );
}

function RightPanelSection({
  children,
  collapsed,
  headerExtra,
  onToggle,
  title,
  value
}: {
  children: ReactNode;
  collapsed: boolean;
  headerExtra?: ReactNode;
  onToggle: () => void;
  title: string;
  value?: string;
}) {
  return (
    <section className={`right-panel-section ${collapsed ? "collapsed" : ""}`}>
      <button className="right-collapsible-header" onClick={onToggle} type="button">
        <span className="panel-arrow">{collapsed ? "▼" : "▲"}</span>
        <span className="panel-title">{title}</span>
        {value ? <span className="panel-value">{value}</span> : null}
        {headerExtra}
      </button>
      <div className="right-panel-section-body">{children}</div>
    </section>
  );
}

function FundamentalsPanel({
  data,
  displayName,
  error,
  loading,
  symbol
}: {
  data: Fundamentals | null;
  displayName: string;
  error: string | null;
  loading: boolean;
  symbol: string;
}) {
  if (loading) {
    return (
      <div className="fundamentals-panel">
        <div className="fundamentals-title">
          <strong>{displayName}</strong>
          <span>{symbol}</span>
        </div>
        <div className="fundamentals-skeleton">
          {Array.from({ length: 8 }).map((_, index) => (
            <span key={index} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="fundamentals-panel">
      <div className="fundamentals-title">
        <strong>{displayName}</strong>
        <span>{symbol}{data?.name ? " · " + data.name : ""}</span>
      </div>
      {error || !data ? (
        <div className="fundamentals-placeholder inline">
          <p>{error ? "基本面資料暫時無法取得。" : "此標的目前沒有可顯示的基本面資料。"}</p>
        </div>
      ) : (
        <div className="fundamentals-table">
          <FundamentalRow label="P/E" value={formatNumber(data.pe)} />
          <FundamentalRow label="P/B" value={formatNumber(data.pb)} />
          <FundamentalRow label="ROE" tone={data.roe} value={formatOptionalPercent(data.roe)} />
          <FundamentalRow label="EPS (TTM)" tone={data.eps_ttm} value={formatNumber(data.eps_ttm)} />
          <FundamentalRow label="殖利率" value={formatOptionalPercent(data.dividend_yield)} />
          <FundamentalRow label="52W 位置" value={<ProgressValue value={data.week_52_position} />} />
          <FundamentalRow label="Beta" value={formatNumber(data.beta)} />
          <FundamentalRow label="市值" value={formatMarketCap(data.market_cap, data.currency)} />
        </div>
      )}
      <BosRadarChart isFallback={!data?.bos_scores} scores={data?.bos_scores} />
    </div>
  );
}

const myScoreFields: Array<{ key: keyof MyScores; label: string }> = [
  { key: "profit", label: "獲利" },
  { key: "growth", label: "成長" },
  { key: "value", label: "價值" },
  { key: "finance", label: "財務" },
  { key: "momentum", label: "動能" }
];

const emptyMyScores: MyScores = {
  profit: null,
  growth: null,
  value: null,
  finance: null,
  momentum: null
};

function MyScorePanel({ symbol }: { symbol: string }) {
  const [scores, setScores] = useState<MyScores>(emptyMyScores);
  const scoreStorageReadyRef = useRef(false);
  const skipInitialScoreWriteRef = useRef(true);

  useEffect(() => {
    scoreStorageReadyRef.current = false;
    skipInitialScoreWriteRef.current = true;
    const stored = readMyScoreStorage(symbol);
    if (!stored) {
      setScores(emptyMyScores);
      scoreStorageReadyRef.current = true;
      return;
    }

    try {
      setScores(normalizeMyScores(JSON.parse(stored)));
    } catch {
      setScores(emptyMyScores);
    }
    scoreStorageReadyRef.current = true;
  }, [symbol]);

  useEffect(() => {
    if (!scoreStorageReadyRef.current) return;
    if (skipInitialScoreWriteRef.current) {
      skipInitialScoreWriteRef.current = false;
      return;
    }
    writeMyScoreStorage(symbol, scores);
  }, [scores, symbol]);

  function updateScore(key: keyof MyScores, rawValue: string) {
    const nextValue = parseScoreInput(rawValue);
    const nextScores = { ...scores, [key]: nextValue };
    setScores(nextScores);
    writeMyScoreStorage(symbol, nextScores);
  }

  const validScores = myScoreFields
    .map((field) => scores[field.key])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const average = validScores.length > 0
    ? validScores.reduce((sum, value) => sum + value, 0) / validScores.length
    : null;

  return (
    <div className="my-score-panel">
      <div className="my-score-heading">
        <div>
          <strong>我的評分</strong>
          <span>{symbol}</span>
        </div>
        <div className="my-score-average">
          {average === null ? (
            <em>尚未評分</em>
          ) : (
            <>
              <strong>{average.toFixed(1)}</strong>
              <span>平均</span>
            </>
          )}
        </div>
      </div>
      <div className="my-score-grid">
        {myScoreFields.map((field) => (
          <label className="my-score-field" key={field.key}>
            <span>{field.label}</span>
            <input
              inputMode="decimal"
              max={10}
              min={0}
              onInput={(event) => updateScore(field.key, event.currentTarget.value)}
              placeholder="-"
              step={0.5}
              type="number"
              value={scores[field.key] ?? ""}
            />
          </label>
        ))}
      </div>
    </div>
  );
}

function myScoreStorageKey(symbol: string) {
  return `myScore_${symbol}`;
}

function readMyScoreStorage(symbol: string) {
  if (typeof window === "undefined") return null;
  const key = myScoreStorageKey(symbol);
  try {
    const stored = window.localStorage.getItem(key);
    if (stored) return stored;
  } catch {
    // Some embedded browser contexts can block localStorage; cookie keeps the UI usable.
  }
  return readCookieValue(key) ?? readWindowNameValue(key);
}

function writeMyScoreStorage(symbol: string, scores: MyScores) {
  if (typeof window === "undefined") return;
  const key = myScoreStorageKey(symbol);
  const payload = JSON.stringify(scores);
  try {
    window.localStorage.setItem(key, payload);
  } catch {
    // Keep going and use the cookie fallback below.
  }
  writeCookieValue(key, payload);
  writeWindowNameValue(key, payload);
}

function readCookieValue(key: string) {
  if (typeof document === "undefined") return null;
  try {
    const encodedKey = encodeURIComponent(key);
    const match = document.cookie
      .split("; ")
      .find((item) => item.startsWith(`${encodedKey}=`));
    return match ? decodeURIComponent(match.slice(encodedKey.length + 1)) : null;
  } catch {
    return null;
  }
}

function writeCookieValue(key: string, value: string) {
  if (typeof document === "undefined") return;
  try {
    document.cookie = `${encodeURIComponent(key)}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
  } catch {
    // Ignore and continue with window.name fallback.
  }
}

function readWindowNameValue(key: string) {
  if (typeof window === "undefined") return null;
  const storage = parseWindowNameStorage();
  return typeof storage[key] === "string" ? storage[key] : null;
}

function writeWindowNameValue(key: string, value: string) {
  if (typeof window === "undefined") return;
  const storage = parseWindowNameStorage();
  storage[key] = value;
  window.name = JSON.stringify({ tradingDashboardMyScores: storage });
}

function parseWindowNameStorage() {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.name || "{}");
    const storage = parsed?.tradingDashboardMyScores;
    return storage && typeof storage === "object" ? storage as Record<string, string> : {};
  } catch {
    return {};
  }
}

function normalizeMyScores(value: unknown): MyScores {
  if (!value || typeof value !== "object") return emptyMyScores;
  const record = value as Record<string, unknown>;
  return {
    profit: normalizeScoreValue(record.profit),
    growth: normalizeScoreValue(record.growth),
    value: normalizeScoreValue(record.value),
    finance: normalizeScoreValue(record.finance),
    momentum: normalizeScoreValue(record.momentum)
  };
}

function normalizeScoreValue(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return null;
  return Math.max(0, Math.min(10, Math.round(number * 2) / 2));
}

function parseScoreInput(value: string) {
  if (value.trim() === "") return null;
  return normalizeScoreValue(value);
}

function BosRadarChart({ isFallback = false, scores }: { isFallback?: boolean; scores?: BosScores | null }) {
  const axes: Array<{ key: keyof BosScores; label: string }> = [
    { key: "profitability", label: "獲利" },
    { key: "growth", label: "成長" },
    { key: "value", label: "價值" },
    { key: "financial", label: "財務" },
    { key: "momentum", label: "動能" }
  ];
  const values = axes.map((axis) => clampScore(scores?.[axis.key] ?? 5));
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  const center = 80;
  const radius = 48;
  const polygonPoints = values
    .map((value, index) => radarPoint(index, axes.length, radius * (value / 10), center))
    .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(" ");

  return (
    <div className="bos-radar-card">
      <div className="bos-radar-heading">
        <div>
          <strong>BOS 五維評分</strong>
          <span>{isFallback ? "暫以中性值顯示" : "0-10"}</span>
        </div>
        <div className="bos-score-average">
          <strong>{average.toFixed(1)}</strong>
          <span>平均</span>
        </div>
      </div>
      <div className="bos-radar-layout">
        <svg className="bos-radar-svg" height="160" role="img" viewBox="0 0 160 160" width="160" aria-label="BOS 五維雷達圖">
          {[0.25, 0.5, 0.75, 1].map((ratio) => (
            <polygon
              className="bos-radar-grid"
              key={ratio}
              points={axes
                .map((_, index) => radarPoint(index, axes.length, radius * ratio, center))
                .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
                .join(" ")}
            />
          ))}
          {axes.map((axis, index) => {
            const edge = radarPoint(index, axes.length, radius, center);
            const label = radarPoint(index, axes.length, radius + 18, center);
            return (
              <g key={axis.key}>
                <line className="bos-radar-axis" x1={center} x2={edge.x} y1={center} y2={edge.y} />
                <text className="bos-radar-label" x={label.x} y={label.y}>
                  {axis.label}
                </text>
              </g>
            );
          })}
          <polygon className="bos-radar-area" points={polygonPoints} />
        </svg>
        <div className="bos-score-list">
          {axes.map((axis, index) => (
            <div className="bos-score-row" key={axis.key}>
              <span>{axis.label}</span>
              <strong>{values[index].toFixed(1)}</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function radarPoint(index: number, total: number, radius: number, center: number) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  return {
    x: center + Math.cos(angle) * radius,
    y: center + Math.sin(angle) * radius
  };
}

function clampScore(value: number) {
  if (!Number.isFinite(value)) return 5;
  return Math.max(0, Math.min(10, value));
}

function FundamentalRow({
  label,
  tone,
  value
}: {
  label: string;
  tone?: number | null;
  value: ReactNode;
}) {
  return (
    <div className="fundamental-row">
      <span>{label}</span>
      <strong className={classForChange(tone)}>{value}</strong>
    </div>
  );
}

function ProgressValue({ value }: { value: number | null }) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const clampedValue = Math.max(0, Math.min(100, value));
  const positionClass = clampedValue < 25 ? "is-low" : clampedValue <= 75 ? "is-mid" : "is-high";
  return (
    <span className="week52-progress">
      <i className={`fundamentals-progress-fill ${positionClass}`} style={{ width: `${clampedValue}%` }} />
      <em>{value.toFixed(0)}%</em>
    </span>
  );
}

function MarketChart({
  candles,
  timeframe,
  visibleMa,
  showBollinger,
  warning
}: {
  candles: Candle[];
  indicators: Indicators | null;
  timeframe: Timeframe;
  visibleMa: Record<MaKey, boolean>;
  showBollinger: boolean;
  warning: string | null;
}) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chartColors = getChartColors();

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: chartColors.background },
        textColor: chartColors.text
      },
      grid: {
        vertLines: { color: chartColors.grid },
        horzLines: { color: chartColors.grid }
      },
      rightPriceScale: {
        borderColor: chartColors.border
      },
      timeScale: {
        borderColor: chartColors.border,
        timeVisible: true
      }
    });

    chartRef.current = chart;
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: chartColors.up,
      downColor: chartColors.down,
      borderUpColor: chartColors.up,
      borderDownColor: chartColors.down,
      wickUpColor: chartColors.up,
      wickDownColor: chartColors.down
    });
    const emaSeries = chart.addSeries(LineSeries, {
      color: chartColors.ma20,
      lineWidth: 2,
      priceLineVisible: false
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: chartColors.volumeUp,
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: false
    }, 1);

    const panes = chart.panes();
    panes[0]?.setStretchFactor(0.78);
    panes[1]?.setStretchFactor(0.22);

    const chartCandles = candles.map((item) => ({
      time: toChartTime(item.time),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close
    }));

    candleSeries.setData(
      chartCandles
    );

    emaSeries.setData([]);

    maDefinitions.forEach((definition) => {
      if (!visibleMa[definition.key]) return;
      if (showBollinger && definition.key === "ma20") return;
      const series = chart.addSeries(LineSeries, {
        color: readCssVar(definition.colorVar, definition.fallback),
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false
      });
      series.setData(calcMA(candles, definition.period));
    });

    if (showBollinger) {
      const bb = calcBB(candles);
      const bandArea = chart.addSeries(AreaSeries, {
        lineColor: "rgba(255, 255, 255, 0)",
        topColor: chartColors.bbArea,
        bottomColor: "rgba(255, 255, 255, 0)",
        priceLineVisible: false,
        lastValueVisible: false
      });
      bandArea.setData(bb.map((item) => ({ time: item.time, value: item.upper })));

      const upper = chart.addSeries(LineSeries, {
        color: chartColors.bbBand,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false
      });
      const middle = chart.addSeries(LineSeries, {
        color: chartColors.ma20,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false
      });
      const lower = chart.addSeries(LineSeries, {
        color: chartColors.bbBand,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false
      });
      upper.setData(bb.map((item) => ({ time: item.time, value: item.upper })));
      middle.setData(bb.map((item) => ({ time: item.time, value: item.middle })));
      lower.setData(bb.map((item) => ({ time: item.time, value: item.lower })));
    }

    volumeSeries.setData(
      candles.map((item) => ({
        time: toChartTime(item.time),
        value: item.volume ?? 0,
        color: item.close >= item.open ? chartColors.volumeUp : chartColors.volumeDown
      }))
    );

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, showBollinger, theme, visibleMa]);

  return (
    <div className="chart-wrap">
      <div ref={containerRef} className="chart-canvas" />
      {timeframe === "5m" ? <div className="delay-badge">⚠ 5m 資料延遲 15 分鐘（美股）/ 20 分鐘（台股）</div> : null}
      {warning ? <div className="chart-warning-badge">{warning}</div> : null}
      {candles.length === 0 ? <div className="chart-empty">No OHLCV data</div> : null}
    </div>
  );
}

function IndicatorPanel({
  activeIndicator,
  candles,
  indicators,
  onSelectIndicator
}: {
  activeIndicator: IndicatorTab;
  candles: Candle[];
  indicators: Indicators | null;
  onSelectIndicator: (tab: IndicatorTab) => void;
}) {
  return (
    <div className="indicator-panel">
      <div className="indicator-tabs">
        {(["rsi", "kd", "macd"] as IndicatorTab[]).map((tab) => (
          <button className={tab === activeIndicator ? "selected" : ""} key={tab} onClick={() => onSelectIndicator(tab)} type="button">
            {tab.toUpperCase()}
          </button>
        ))}
        <span>
          RSI {formatNumber(indicators?.rsi_14)} · K {formatNumber(indicators?.kd_9_3?.k)} · MACD {formatNumber(indicators?.macd?.macd)}
        </span>
      </div>
      <IndicatorSubChart activeIndicator={activeIndicator} candles={candles} />
    </div>
  );
}

function IndicatorSubChart({ activeIndicator, candles }: { activeIndicator: IndicatorTab; candles: Candle[] }) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chartColors = getChartColors();
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: chartColors.background },
        textColor: chartColors.text
      },
      grid: {
        vertLines: { color: chartColors.grid },
        horzLines: { color: chartColors.grid }
      },
      rightPriceScale: {
        borderColor: chartColors.border,
        scaleMargins: { top: 0.12, bottom: 0.12 }
      },
      timeScale: {
        borderColor: chartColors.border,
        timeVisible: true
      }
    });

    if (activeIndicator === "rsi") {
      const rsi = calcRSI(candles);
      addGuideLine(chart, candles, 70, chartColors.guideHot);
      addGuideLine(chart, candles, 30, chartColors.guideCool);
      const series = chart.addSeries(LineSeries, {
        color: chartColors.ma60,
        lineWidth: 1,
        priceLineVisible: false
      });
      series.setData(rsi);
    }

    if (activeIndicator === "kd") {
      const kd = calcKD(candles);
      addGuideLine(chart, candles, 80, chartColors.guideHot);
      addGuideLine(chart, candles, 20, chartColors.guideCool);
      const kSeries = chart.addSeries(LineSeries, {
        color: chartColors.ma10,
        lineWidth: 1,
        priceLineVisible: false
      });
      const dSeries = chart.addSeries(LineSeries, {
        color: chartColors.ma20,
        lineWidth: 1,
        priceLineVisible: false
      });
      kSeries.setData(kd.map((item) => ({ time: item.time, value: item.k })));
      dSeries.setData(kd.map((item) => ({ time: item.time, value: item.d })));
    }

    if (activeIndicator === "macd") {
      const macd = calcMACD(candles);
      addGuideLine(chart, candles, 0, chartColors.zero);
      const histogram = chart.addSeries(HistogramSeries, {
        color: chartColors.up,
        priceLineVisible: false,
        lastValueVisible: false
      });
      const dif = chart.addSeries(LineSeries, {
        color: chartColors.macdDif,
        lineWidth: 1,
        priceLineVisible: false
      });
      const dea = chart.addSeries(LineSeries, {
        color: chartColors.ma10,
        lineWidth: 1,
        priceLineVisible: false
      });
      histogram.setData(macd.map((item) => ({ time: item.time, value: item.histogram, color: item.histogram >= 0 ? chartColors.up : chartColors.down })));
      dif.setData(macd.map((item) => ({ time: item.time, value: item.dif })));
      dea.setData(macd.map((item) => ({ time: item.time, value: item.dea })));
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
    };
  }, [activeIndicator, candles, theme]);

  return <div ref={containerRef} className="indicator-chart-canvas" />;
}

function TechnicalSignals({ indicators, quote, symbol }: { indicators: Indicators | null; quote: MarketQuote | null; symbol: string }) {
  const signals: Array<{ label: string; value: string; tone?: number | null }> = [];
  signals.push({
    label: `${symbol} 日內變動`,
    value: formatPercent(quote?.change_pct),
    tone: quote?.change_pct
  });

  if (indicators?.rsi_14 !== null && indicators?.rsi_14 !== undefined) {
    const rsiTone = indicators.rsi_14 >= 70 ? -1 : indicators.rsi_14 <= 30 ? 1 : 0;
    signals.push({
      label: indicators.rsi_14 >= 70 ? "RSI 偏熱" : indicators.rsi_14 <= 30 ? "RSI 偏冷" : "RSI 中性",
      value: formatNumber(indicators.rsi_14),
      tone: rsiTone
    });
  }

  if (indicators?.macd?.histogram !== null && indicators?.macd?.histogram !== undefined) {
    signals.push({
      label: indicators.macd.histogram >= 0 ? "MACD 動能轉強" : "MACD 動能轉弱",
      value: formatNumber(indicators.macd.histogram),
      tone: indicators.macd.histogram
    });
  }

  if (indicators?.bb_20_2?.upper && quote?.price) {
    const bbPosition = quote.price >= indicators.bb_20_2.upper ? "接近上軌" : quote.price <= (indicators.bb_20_2.lower ?? 0) ? "接近下軌" : "通道內";
    signals.push({
      label: `布林通道 ${bbPosition}`,
      value: formatNumber(quote.price),
      tone: bbPosition === "接近上軌" ? 1 : bbPosition === "接近下軌" ? -1 : 0
    });
  }

  if (indicators?.kd_9_3?.k !== null && indicators?.kd_9_3?.d !== null && indicators?.kd_9_3?.k !== undefined && indicators?.kd_9_3?.d !== undefined) {
    const kdDiff = indicators.kd_9_3.k - indicators.kd_9_3.d;
    signals.push({
      label: kdDiff >= 0 ? "KD K>D" : "KD K<D",
      value: formatNumber(kdDiff),
      tone: kdDiff
    });
  }

  return (
    <div className="signal-list">
      {signals.map((signal) => (
        <div className="signal-item" key={signal.label}>
          <span>{signal.label}</span>
          <strong className={classForChange(signal.tone)}>{signal.value}</strong>
        </div>
      ))}
    </div>
  );
}

function PanelHeader({ title, value }: { title: string; value: string }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      <span>{value}</span>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: number | null }) {
  return (
    <div className="summary-item metric">
      <span className="summary-label">{label}</span>
      <strong className={`summary-value ${classForChange(tone)}`}>{value}</strong>
    </div>
  );
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new Error(`${path} HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

async function fetchQuotes(symbols: string[]) {
  if (symbols.length === 0) return [];
  const query = new URLSearchParams({
    symbols: symbols.join(","),
    timeframe: "1d",
    realtime: "true"
  });
  const response = await fetchJson<ApiResponse<MarketQuote[]>>(`/api/v1/market/quote?${query.toString()}`);
  return response.data;
}

function normalizeSymbol(value: string) {
  return value.trim().toUpperCase();
}

function providerForSymbol(symbol: string) {
  return symbol.endsWith("USDT") ? "binance" : "yfinance";
}

function timeframeLabel(value: Timeframe) {
  return value === "5m" ? "5m" : value.toUpperCase();
}

function toChartTime(value: string): Time {
  return Math.floor(new Date(value).getTime() / 1000) as Time;
}

function calcMA(candles: Candle[], period: number) {
  const closes = candles.map((item) => item.close);
  return candles
    .map((item, index) => {
      if (index < period - 1) return null;
      const slice = closes.slice(index - period + 1, index + 1);
      const sum = slice.reduce((total, value) => total + value, 0);
      return { time: toChartTime(item.time), value: sum / period };
    })
    .filter((item): item is { time: Time; value: number } => item !== null);
}

function calcBB(candles: Candle[], period = 20, multiplier = 2) {
  const closes = candles.map((item) => item.close);
  return candles
    .map((item, index) => {
      if (index < period - 1) return null;
      const slice = closes.slice(index - period + 1, index + 1);
      const mean = slice.reduce((total, value) => total + value, 0) / period;
      const variance = slice.reduce((total, value) => total + (value - mean) ** 2, 0) / period;
      const std = Math.sqrt(variance);
      return {
        time: toChartTime(item.time),
        upper: mean + multiplier * std,
        middle: mean,
        lower: mean - multiplier * std
      };
    })
    .filter((item): item is { time: Time; upper: number; middle: number; lower: number } => item !== null);
}

function calcEMAValues(values: number[], period: number) {
  const multiplier = 2 / (period + 1);
  let ema = values[0] ?? 0;
  return values.map((value, index) => {
    ema = index === 0 ? value : value * multiplier + ema * (1 - multiplier);
    return ema;
  });
}

function calcRSI(candles: Candle[], period = 14) {
  if (candles.length <= period) return [];
  const result: Array<{ time: Time; value: number }> = [];
  let avgGain = 0;
  let avgLoss = 0;

  for (let index = 1; index <= period; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    if (change >= 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }

  avgGain /= period;
  avgLoss /= period;

  for (let index = period; index < candles.length; index += 1) {
    if (index > period) {
      const change = candles[index].close - candles[index - 1].close;
      const gain = Math.max(change, 0);
      const loss = Math.max(-change, 0);
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
    }
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const value = avgLoss === 0 ? 100 : 100 - 100 / (1 + rs);
    result.push({ time: toChartTime(candles[index].time), value });
  }

  return result;
}

function calcKD(candles: Candle[], period = 9) {
  const result: Array<{ time: Time; k: number; d: number }> = [];
  let k = 50;
  let d = 50;

  candles.forEach((item, index) => {
    if (index < period - 1) return;
    const window = candles.slice(index - period + 1, index + 1);
    const lowest = Math.min(...window.map((candle) => candle.low));
    const highest = Math.max(...window.map((candle) => candle.high));
    const rsv = highest === lowest ? 50 : ((item.close - lowest) / (highest - lowest)) * 100;
    k = k * (2 / 3) + rsv * (1 / 3);
    d = d * (2 / 3) + k * (1 / 3);
    result.push({ time: toChartTime(item.time), k, d });
  });

  return result;
}

function calcMACD(candles: Candle[]) {
  const closes = candles.map((item) => item.close);
  const ema12 = calcEMAValues(closes, 12);
  const ema26 = calcEMAValues(closes, 26);
  const difValues = closes.map((_, index) => ema12[index] - ema26[index]);
  const deaValues = calcEMAValues(difValues, 9);
  return candles.map((item, index) => ({
    time: toChartTime(item.time),
    dif: difValues[index],
    dea: deaValues[index],
    histogram: (difValues[index] - deaValues[index]) * 2
  }));
}

function addGuideLine(chart: IChartApi, candles: Candle[], value: number, color: string) {
  if (candles.length === 0) return;
  const first = toChartTime(candles[0].time);
  const last = toChartTime(candles[candles.length - 1].time);
  const guide = chart.addSeries(LineSeries, {
    color,
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    priceLineVisible: false,
    lastValueVisible: false
  });
  guide.setData([
    { time: first, value },
    { time: last, value }
  ]);
}

function calculateLatestIndicators(candles: Candle[]): Indicators | null {
  if (candles.length === 0) return null;
  const latestRsi = lastValue(calcRSI(candles))?.value ?? null;
  const latestKd = lastValue(calcKD(candles));
  const latestMacd = lastValue(calcMACD(candles));
  const latestBb = lastValue(calcBB(candles));
  const latestMa20 = lastValue(calcMA(candles, 20))?.value ?? null;
  return {
    rsi_14: latestRsi,
    macd: {
      macd: latestMacd?.dif ?? null,
      signal: latestMacd?.dea ?? null,
      histogram: latestMacd?.histogram ?? null
    },
    bb_20_2: {
      middle: latestBb?.middle ?? null,
      upper: latestBb?.upper ?? null,
      lower: latestBb?.lower ?? null
    },
    kd_9_3: {
      k: latestKd?.k ?? null,
      d: latestKd?.d ?? null
    },
    ema_20: latestMa20,
    atr_14: calcATR(candles),
    obv: calcOBV(candles)
  };
}

function calcATR(candles: Candle[], period = 14) {
  if (candles.length < period + 1) return null;
  const trs = candles.slice(1).map((item, index) => {
    const previousClose = candles[index].close;
    return Math.max(item.high - item.low, Math.abs(item.high - previousClose), Math.abs(item.low - previousClose));
  });
  const slice = trs.slice(-period);
  return slice.reduce((total, value) => total + value, 0) / period;
}

function calcOBV(candles: Candle[]) {
  if (candles.length === 0) return null;
  return candles.slice(1).reduce((obv, item, index) => {
    const previousClose = candles[index].close;
    const volume = item.volume ?? 0;
    if (item.close > previousClose) return obv + volume;
    if (item.close < previousClose) return obv - volume;
    return obv;
  }, 0);
}

function lastValue<T>(items: T[]) {
  return items.length > 0 ? items[items.length - 1] : undefined;
}

function limitForRange(timeframe: Timeframe, range: RangeValue) {
  const byRange: Record<RangeValue, number> = {
    "1d": timeframe === "5m" ? 120 : 30,
    "3d": 240,
    "1w": timeframe === "5m" ? 600 : 120,
    "2w": 1200,
    "1m": timeframe === "5m" ? 2000 : timeframe === "1h" ? 720 : 40,
    "3m": timeframe === "1h" ? 1500 : 80,
    "6m": timeframe === "1h" ? 3000 : 140,
    "1y": timeframe === "1h" ? 5000 : 260,
    "2y": 5000,
    "3y": 780,
    "5y": 1300,
    "10y": 2600
  };
  return byRange[range] ?? 500;
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Math.abs(value) > 1000 ? 2 : 4
  }).format(value);
}

function formatCompact(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

function formatOptionalPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(2)}%`;
}

function formatMarketCap(value: number | null | undefined, currency: string | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const prefix = currency === "TWD" ? "NT$" : currency === "USD" ? "US$" : currency ? `${currency} ` : "";
  return `${prefix}${formatCompact(value)}`;
}

function todayInputDate() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

function addDaysToInputDate(value: string, days: number) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return todayInputDate();
  date.setDate(date.getDate() + days);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

function formatNoteDateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short"
  }).format(date);
}

function formatSavedTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function noteStatusText(status: NoteStatus, lastSavedAt: string | null) {
  if (status === "loading") return "載入中…";
  if (status === "editing") return "編輯中…";
  if (status === "saving") return "儲存中…";
  if (status === "failed") return "儲存失敗 ⚠";
  if (status === "saved") return `已儲存 ${formatSavedTime(lastSavedAt)}`;
  return "尚未儲存";
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function classForChange(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}
