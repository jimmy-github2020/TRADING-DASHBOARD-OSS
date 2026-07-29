"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, History, Loader2, Play, RefreshCw } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

type ApiResponse<T> = {
  data: T;
  meta: Record<string, unknown>;
  timestamp: string;
};

type Strategy = {
  id: string;
  name: string;
  conditions: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
};

type EquityPoint = {
  timestamp: string;
  value: number;
};

type Trade = {
  symbol: string;
  entry_date: string;
  exit_date: string;
  holding_days: number;
  entry_price: number;
  exit_price: number;
  return_pct: number;
};

type BacktestResult = {
  id: string;
  strategy_id: string;
  strategy_name?: string;
  symbols: string[];
  start_date: string;
  end_date: string;
  timeframe: "1d" | "1h";
  initial_capital: number;
  commission: number;
  total_return_pct: number;
  annual_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  total_trades: number;
  avg_holding_days: number;
  profit_factor: number;
  equity_curve: EquityPoint[];
  trades: Trade[];
  created_at: string;
};

type BacktestRunPayload = {
  strategy_id: string;
  symbols: string[];
  start_date: string;
  end_date: string;
  timeframe: "1d" | "1h";
  initial_capital: number;
  commission: number;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const symbolOptions = [
  { symbol: "0050.TW", name: "台灣50" },
  { symbol: "006208.TW", name: "富邦台50" },
  { symbol: "2330.TW", name: "台積電" },
  { symbol: "2317.TW", name: "鴻海" },
  { symbol: "2882.TW", name: "國泰金" },
  { symbol: "^GSPC", name: "S&P 500" },
  { symbol: "^NDX", name: "Nasdaq 100" },
  { symbol: "^VIX", name: "VIX 恐慌" },
  { symbol: "GC=F", name: "黃金" },
  { symbol: "CL=F", name: "原油 WTI" }
];

const defaultSymbols = ["2330.TW", "0050.TW"];

export default function BacktestPage() {
  const queryClient = useQueryClient();
  const defaultDates = useMemo(() => getDefaultDates(), []);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState(defaultSymbols);
  const [startDate, setStartDate] = useState(defaultDates.startDate);
  const [endDate, setEndDate] = useState(defaultDates.endDate);
  const [timeframe, setTimeframe] = useState<"1d" | "1h">("1d");
  const [initialCapital, setInitialCapital] = useState(100000);
  const [commission, setCommission] = useState(0.001);
  const [activeResult, setActiveResult] = useState<BacktestResult | null>(null);
  const [showTrades, setShowTrades] = useState(true);

  const strategiesQuery = useQuery({
    queryKey: ["backtest", "strategies"],
    queryFn: () => fetchJson<ApiResponse<Strategy[]>>("/api/v1/strategies"),
    staleTime: 60 * 1000
  });

  const historyQuery = useQuery({
    queryKey: ["backtest", "history"],
    queryFn: () => fetchJson<ApiResponse<BacktestResult[]>>("/api/v1/backtest/list?limit=10"),
    staleTime: 30 * 1000
  });

  const runMutation = useMutation({
    mutationFn: (payload: BacktestRunPayload) =>
      fetchJson<ApiResponse<BacktestResult>>("/api/v1/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }),
    onSuccess: (response) => {
      setActiveResult(response.data);
      queryClient.invalidateQueries({ queryKey: ["backtest", "history"] });
    }
  });

  const loadResultMutation = useMutation({
    mutationFn: (id: string) => fetchJson<ApiResponse<BacktestResult>>(`/api/v1/backtest/${id}`),
    onSuccess: (response) => setActiveResult(response.data)
  });

  const strategies = strategiesQuery.data?.data ?? [];
  const history = historyQuery.data?.data ?? [];
  const selectedStrategy = strategies.find((strategy) => strategy.id === selectedStrategyId);
  const canRun = selectedStrategyId && selectedSymbols.length > 0 && startDate && endDate && !runMutation.isPending;

  function toggleSymbol(symbol: string) {
    setSelectedSymbols((current) =>
      current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]
    );
  }

  function runBacktest() {
    if (!canRun) return;
    runMutation.mutate({
      strategy_id: selectedStrategyId,
      symbols: selectedSymbols,
      start_date: startDate,
      end_date: endDate,
      timeframe,
      initial_capital: initialCapital,
      commission
    });
  }

  return (
    <main className="backtest-shell">
      <header className="backtest-header">
        <div>
          <p className="panel-kicker">Phase T3</p>
          <h1>回測系統</h1>
          <span>選擇 T2 策略、標的與期間，檢視績效、資產曲線與交易紀錄。</span>
        </div>
        <button
          className="secondary-action"
          onClick={() => historyQuery.refetch()}
          type="button"
          disabled={historyQuery.isFetching}
        >
          {historyQuery.isFetching ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
          重新整理
        </button>
      </header>

      <section className="backtest-workspace">
        <div className="backtest-card backtest-form-card">
          <div className="backtest-card-header">
            <div>
              <h2>回測設定</h2>
              <span>{selectedStrategy ? selectedStrategy.name : "尚未選擇策略"}</span>
            </div>
          </div>

          {strategiesQuery.isLoading ? (
            <FormSkeleton />
          ) : strategiesQuery.isError ? (
            <div className="analysis-error">{errorMessage(strategiesQuery.error)}</div>
          ) : (
            <div className="backtest-form">
              <label className="field-block">
                <span>策略</span>
                <select value={selectedStrategyId} onChange={(event) => setSelectedStrategyId(event.target.value)}>
                  <option value="">選擇策略</option>
                  {strategies.map((strategy) => (
                    <option key={strategy.id} value={strategy.id}>
                      {strategy.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="field-block">
                <span>標的</span>
                <div className="backtest-symbol-grid">
                  {symbolOptions.map((option) => (
                    <label className="symbol-check" key={option.symbol}>
                      <input
                        type="checkbox"
                        checked={selectedSymbols.includes(option.symbol)}
                        onChange={() => toggleSymbol(option.symbol)}
                      />
                      <span>{option.name}</span>
                      <em>{option.symbol}</em>
                    </label>
                  ))}
                </div>
              </div>

              <div className="form-grid two">
                <label className="field-block">
                  <span>開始日期</span>
                  <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                </label>
                <label className="field-block">
                  <span>結束日期</span>
                  <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
                </label>
              </div>

              <div className="period-tabs" aria-label="回測時間框架">
                {(["1d", "1h"] as const).map((item) => (
                  <button
                    className={timeframe === item ? "selected" : ""}
                    key={item}
                    onClick={() => setTimeframe(item)}
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>

              <div className="form-grid two">
                <label className="field-block">
                  <span>初始資金</span>
                  <input
                    type="number"
                    min={1000}
                    step={1000}
                    value={initialCapital}
                    onChange={(event) => setInitialCapital(Number(event.target.value))}
                  />
                </label>
                <label className="field-block">
                  <span>手續費率</span>
                  <input
                    type="number"
                    min={0}
                    step={0.0001}
                    value={commission}
                    onChange={(event) => setCommission(Number(event.target.value))}
                  />
                </label>
              </div>

              {runMutation.isError ? <div className="analysis-error">{errorMessage(runMutation.error)}</div> : null}

              <button className="primary-action wide" disabled={!canRun} onClick={runBacktest} type="button">
                {runMutation.isPending ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
                執行回測
              </button>
            </div>
          )}
        </div>

        <div className="backtest-card backtest-report-card">
          <div className="backtest-card-header">
            <div>
              <h2>績效報表</h2>
              <span>{activeResult ? `${activeResult.symbols.join(", ")} · ${activeResult.timeframe}` : "等待回測結果"}</span>
            </div>
          </div>

          {runMutation.isPending || loadResultMutation.isPending ? (
            <ReportSkeleton />
          ) : activeResult ? (
            <BacktestReport result={activeResult} showTrades={showTrades} setShowTrades={setShowTrades} />
          ) : (
            <div className="backtest-empty">左側設定完成後執行回測，結果會顯示在這裡。</div>
          )}
        </div>
      </section>

      <section className="backtest-card history-card">
        <div className="backtest-card-header">
          <div>
            <h2>回測歷史</h2>
            <span>最近 10 筆</span>
          </div>
          <History size={22} />
        </div>

        {historyQuery.isLoading ? (
          <HistorySkeleton />
        ) : historyQuery.isError ? (
          <div className="analysis-error">{errorMessage(historyQuery.error)}</div>
        ) : history.length > 0 ? (
          <div className="history-list">
            {history.map((item) => (
              <button className="history-row" key={item.id} onClick={() => loadResultMutation.mutate(item.id)} type="button">
                <span>
                  <strong>{item.strategy_name ?? item.strategy_id}</strong>
                  <em>{item.symbols.join(", ")}</em>
                </span>
                <span>{formatDate(item.created_at)}</span>
                <strong className={valueTone(item.total_return_pct)}>{formatSignedPercent(item.total_return_pct)}</strong>
                <em>Sharpe {formatRatio(item.sharpe_ratio)}</em>
              </button>
            ))}
          </div>
        ) : (
          <div className="backtest-empty">尚無回測紀錄。</div>
        )}
      </section>
    </main>
  );
}

function BacktestReport({
  result,
  showTrades,
  setShowTrades
}: {
  result: BacktestResult;
  showTrades: boolean;
  setShowTrades: (value: boolean) => void;
}) {
  const kpis = [
    { label: "總報酬", value: formatSignedPercent(result.total_return_pct), tone: valueTone(result.total_return_pct) },
    { label: "年化報酬", value: formatSignedPercent(result.annual_return_pct), tone: valueTone(result.annual_return_pct) },
    { label: "Sharpe", value: formatRatio(result.sharpe_ratio), tone: "" },
    { label: "最大回撤", value: formatPercent(result.max_drawdown_pct), tone: "negative" },
    { label: "勝率", value: formatPercent(result.win_rate), tone: "" },
    { label: "交易次數", value: String(result.total_trades), tone: "" }
  ];

  return (
    <div className="backtest-report">
      <div className="kpi-grid">
        {kpis.map((item) => (
          <div className="kpi-card" key={item.label}>
            <span>{item.label}</span>
            <strong className={item.tone}>{item.value}</strong>
          </div>
        ))}
      </div>

      <EquityCurve points={result.equity_curve} />

      <div className="trade-summary">
        <span>平均持倉 {formatNumber(result.avg_holding_days)} 天</span>
        <span>Profit factor {formatRatio(result.profit_factor)}</span>
        <span>{result.start_date} 至 {result.end_date}</span>
      </div>

      <button className="trade-toggle" onClick={() => setShowTrades(!showTrades)} type="button">
        {showTrades ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        交易紀錄
      </button>

      {showTrades ? <TradeTable trades={result.trades} /> : null}
    </div>
  );
}

function EquityCurve({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) {
    return <div className="backtest-empty">資產曲線資料不足。</div>;
  }

  const width = 760;
  const height = 280;
  const padding = 24;
  const values = points.map((point) => point.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || 1;
  const coords = points.map((point, index) => {
    const x = padding + (index / (points.length - 1)) * (width - padding * 2);
    const y = height - padding - ((point.value - minValue) / range) * (height - padding * 2);
    return { x, y, value: point.value };
  });

  const drawdown = buildDrawdownArea(points, coords, height, padding);
  const line = coords.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="equity-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="資產曲線與回撤">
        <defs>
          <linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#00d4aa" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#00d4aa" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path className="drawdown-area" d={drawdown} />
        <polygon className="equity-area" points={`${line} ${coords.at(-1)?.x},${height - padding} ${coords[0].x},${height - padding}`} />
        <polyline className="equity-line" points={line} />
      </svg>
      <div className="chart-scale">
        <span>{formatCurrency(maxValue)}</span>
        <span>{formatCurrency(minValue)}</span>
      </div>
    </div>
  );
}

function buildDrawdownArea(points: EquityPoint[], coords: Array<{ x: number; y: number; value: number }>, height: number, padding: number) {
  let peak = points[0]?.value ?? 0;
  const baseline = height - padding;
  const area = coords.map((coord, index) => {
    peak = Math.max(peak, points[index].value);
    const drawdownPct = peak > 0 ? (peak - points[index].value) / peak : 0;
    const y = baseline - drawdownPct * 90;
    return `${coord.x},${y}`;
  });
  return `M ${coords[0].x},${baseline} L ${area.join(" L ")} L ${coords.at(-1)?.x ?? coords[0].x},${baseline} Z`;
}

function TradeTable({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) {
    return <div className="backtest-empty">此區間沒有完成交易。</div>;
  }

  return (
    <div className="trade-table-wrap">
      <table className="trade-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>Days</th>
            <th>Return</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade, index) => (
            <tr key={`${trade.symbol}-${trade.entry_date}-${index}`}>
              <td>{trade.symbol}</td>
              <td>{formatDate(trade.entry_date)}</td>
              <td>{formatDate(trade.exit_date)}</td>
              <td>{trade.holding_days}</td>
              <td className={valueTone(trade.return_pct)}>{formatSignedPercent(trade.return_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FormSkeleton() {
  return (
    <div className="backtest-skeleton-stack">
      {Array.from({ length: 7 }).map((_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

function ReportSkeleton() {
  return (
    <div className="backtest-report">
      <div className="kpi-grid">
        {Array.from({ length: 6 }).map((_, index) => (
          <div className="kpi-card skeleton-card" key={index} />
        ))}
      </div>
      <div className="chart-skeleton" />
      <div className="backtest-skeleton-stack compact">
        {Array.from({ length: 4 }).map((_, index) => (
          <span key={index} />
        ))}
      </div>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="history-list">
      {Array.from({ length: 5 }).map((_, index) => (
        <div className="history-row skeleton-history" key={index} />
      ))}
    </div>
  );
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `${path} HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function getDefaultDates() {
  const end = new Date();
  const start = new Date();
  start.setFullYear(end.getFullYear() - 1);
  return {
    startDate: start.toISOString().slice(0, 10),
    endDate: end.toISOString().slice(0, 10)
  };
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value.toFixed(2)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: 0
  }).format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    year: "numeric"
  }).format(new Date(value));
}

function valueTone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "操作失敗";
}
