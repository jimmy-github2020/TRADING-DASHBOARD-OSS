"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Clock3, Loader2, RefreshCw } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

type ApiResponse<T> = {
  data: T;
  meta: Record<string, unknown>;
  timestamp: string;
};

type CorrelationResponse = {
  symbols: string[];
  matrix: Array<Array<number | null>>;
  period: Period;
  calculated_at: string;
  data_points: number;
};

type VolatilityItem = {
  symbol: string;
  name: string;
  volatility_pct: number;
  rank: number;
  period_return_pct: number;
  max_drawdown_pct: number;
};

type VolatilityResponse = {
  symbols: string[];
  period: string;
  annualize: boolean;
  calculated_at: string;
  data_points: number;
  items: VolatilityItem[];
};

type SectorRotationItem = {
  rank: number;
  symbol: string;
  sector_name: string;
  period_return_pct: number;
  relative_return_pct: number;
  momentum_score: number;
  volatility_pct: number;
  sharpe_ratio: number;
  rs_score: number;
};

type SectorRotationResponse = {
  period: string;
  benchmark: string;
  benchmark_return_pct: number;
  calculated_at: string;
  data_points: number;
  items: SectorRotationItem[];
};

type StockRankingItem = {
  symbol: string;
  name: string;
  composite_score: number;
  momentum_score: number;
  low_vol_score: number;
  rs_score: number;
  trend_score: number;
  rank: number;
  period_return_pct: number;
  volatility_pct: number;
};

type StockRankingResponse = {
  symbols: string[];
  period: string;
  benchmark: string;
  benchmark_return_pct: number;
  calculated_at: string;
  data_points: number;
  items: StockRankingItem[];
};

type Period = "7d" | "30d" | "90d";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const symbolOptions = [
  { symbol: "0050.TW", name: "台灣50" },
  { symbol: "2330.TW", name: "台積電" },
  { symbol: "2317.TW", name: "鴻海" },
  { symbol: "006208.TW", name: "富邦台50" },
  { symbol: "^GSPC", name: "S&P 500" },
  { symbol: "^NDX", name: "Nasdaq 100" },
  { symbol: "^VIX", name: "VIX 恐慌指數" },
  { symbol: "GC=F", name: "黃金" },
  { symbol: "CL=F", name: "原油 WTI" },
  { symbol: "DX-Y.NYB", name: "美元指數" },
  { symbol: "^TWII", name: "台灣加權" },
  { symbol: "^DJI", name: "道瓊" },
  { symbol: "^TNX", name: "美債 10Y" },
  { symbol: "^IRX", name: "美債 2Y" }
];

const defaultSymbols = ["0050.TW", "2330.TW", "^GSPC", "^NDX", "^VIX", "GC=F", "CL=F", "DX-Y.NYB"];
const stockRankingSymbols = ["0050.TW", "006208.TW", "2330.TW", "2317.TW", "2882.TW", "^GSPC", "^VIX", "GC=F"];
const periods: Array<{ value: Period; label: string }> = [
  { value: "7d", label: "7天" },
  { value: "30d", label: "30天" },
  { value: "90d", label: "90天" }
];

export default function AnalysisPage() {
  const [selectedSymbols, setSelectedSymbols] = useState(defaultSymbols);
  const [period, setPeriod] = useState<Period>("30d");
  const [annualize, setAnnualize] = useState(true);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      symbols: selectedSymbols.join(","),
      period
    });
    return params.toString();
  }, [selectedSymbols, period]);

  const correlationQuery = useQuery({
    queryKey: ["analysis", "correlation", selectedSymbols, period],
    queryFn: () => fetchJson<ApiResponse<CorrelationResponse>>(`/api/v1/analysis/correlation?${queryString}`),
    enabled: selectedSymbols.length >= 2,
    staleTime: 10 * 60 * 1000
  });

  const volatilityQuery = useQuery({
    queryKey: ["analysis", "volatility", selectedSymbols, period, annualize],
    queryFn: () =>
      fetchJson<ApiResponse<VolatilityResponse>>(
        `/api/v1/analysis/volatility?${new URLSearchParams({
          symbols: selectedSymbols.join(","),
          period: period.replace("d", ""),
          annualize: String(annualize)
        }).toString()}`
      ),
    enabled: selectedSymbols.length >= 2,
    staleTime: 10 * 60 * 1000
  });

  const sectorRotationQuery = useQuery({
    queryKey: ["analysis", "sector-rotation", period],
    queryFn: () =>
      fetchJson<ApiResponse<SectorRotationResponse>>(
        `/api/v1/analysis/sector-rotation?${new URLSearchParams({
          period: period.replace("d", ""),
          benchmark: "SPY"
        }).toString()}`
      ),
    staleTime: 10 * 60 * 1000
  });

  const stockRankingQuery = useQuery({
    queryKey: ["analysis", "stock-ranking", period],
    queryFn: () =>
      fetchJson<ApiResponse<StockRankingResponse>>(
        `/api/v1/analysis/stock-ranking?${new URLSearchParams({
          symbols: stockRankingSymbols.join(","),
          period: period.replace("d", ""),
          benchmark: "^GSPC"
        }).toString()}`
      ),
    staleTime: 10 * 60 * 1000
  });

  const correlation = correlationQuery.data?.data;
  const volatility = volatilityQuery.data?.data;
  const sectorRotation = sectorRotationQuery.data?.data;
  const stockRanking = stockRankingQuery.data?.data;

  function toggleSymbol(symbol: string) {
    setSelectedSymbols((current) =>
      current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]
    );
  }

  return (
    <main className="analysis-shell">
      <header className="analysis-header">
        <div>
          <p className="panel-kicker">Phase T2F</p>
          <h1>量化分析</h1>
          <span>用相關性矩陣與波動率排行觀察市場連動與風險分布。</span>
        </div>
        <div className="analysis-status">
          {correlation ? (
            <>
              <Clock3 size={16} />
              上次計算：{formatTime(correlation.calculated_at)}
            </>
          ) : (
            "等待計算"
          )}
        </div>
      </header>

      <section className="analysis-card">
        <div className="analysis-card-header">
          <div>
            <h2>相關性矩陣</h2>
            <span>{selectedSymbols.length} symbols · {period}</span>
          </div>
          <button
            className="primary-action"
            disabled={selectedSymbols.length < 2 || correlationQuery.isFetching}
            onClick={() => correlationQuery.refetch()}
          >
            {correlationQuery.isFetching ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            計算
          </button>
        </div>

        <div className="analysis-controls">
          <div className="symbol-picker" aria-label="標的選擇">
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

          <div className="period-tabs" aria-label="時間區間">
            {periods.map((item) => (
              <button
                className={period === item.value ? "selected" : ""}
                key={item.value}
                onClick={() => setPeriod(item.value)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {selectedSymbols.length < 2 ? (
          <div className="analysis-empty">請至少選擇 2 個標的。</div>
        ) : correlationQuery.isLoading || correlationQuery.isFetching ? (
          <HeatmapSkeleton count={Math.max(selectedSymbols.length, 2)} />
        ) : correlationQuery.isError ? (
          <div className="analysis-error">{errorMessage(correlationQuery.error)}</div>
        ) : correlation ? (
          <CorrelationHeatmap data={correlation} />
        ) : null}
      </section>

      <section className="analysis-card">
        <div className="analysis-card-header">
          <div>
            <h2>波動率排行</h2>
            <span>{annualize ? "年化波動率" : "原始日標準差"} · {period}</span>
          </div>
          <div className="volatility-tools">
            <label className="annualize-toggle">
              <input type="checkbox" checked={annualize} onChange={(event) => setAnnualize(event.target.checked)} />
              <span>{annualize ? "年化" : "日標準差"}</span>
            </label>
            <BarChart3 size={22} />
          </div>
        </div>

        {selectedSymbols.length < 2 ? (
          <div className="analysis-empty">請至少選擇 2 個標的。</div>
        ) : volatilityQuery.isLoading || volatilityQuery.isFetching ? (
          <VolatilitySkeleton />
        ) : volatilityQuery.isError ? (
          <div className="analysis-error">{errorMessage(volatilityQuery.error)}</div>
        ) : volatility ? (
          <VolatilityRanking data={volatility} />
        ) : (
          <div className="analysis-empty">目前沒有可顯示的波動率資料。</div>
        )}
      </section>

      <section className="analysis-card">
        <div className="analysis-card-header">
          <div>
            <h2>板塊輪動</h2>
            <span>benchmark SPY · {period}</span>
          </div>
          <div className="analysis-status compact">
            {sectorRotation ? `SPY ${formatSignedPercent(sectorRotation.benchmark_return_pct)}` : "等待計算"}
          </div>
        </div>

        {sectorRotationQuery.isLoading || sectorRotationQuery.isFetching ? (
          <SectorRotationSkeleton />
        ) : sectorRotationQuery.isError ? (
          <div className="analysis-error">{errorMessage(sectorRotationQuery.error)}</div>
        ) : sectorRotation ? (
          <SectorRotationPanel data={sectorRotation} />
        ) : (
          <div className="analysis-empty">目前沒有可顯示的板塊輪動資料。</div>
        )}
      </section>

      <section className="analysis-card">
        <div className="analysis-card-header">
          <div>
            <h2>選股排行</h2>
            <span>多因子評分 · benchmark ^GSPC · {period}</span>
          </div>
          <div className="analysis-status compact">
            {stockRanking ? `Top ${stockRanking.items[0]?.symbol ?? "-"}` : "等待計算"}
          </div>
        </div>

        {stockRankingQuery.isLoading || stockRankingQuery.isFetching ? (
          <StockRankingSkeleton />
        ) : stockRankingQuery.isError ? (
          <div className="analysis-error">{errorMessage(stockRankingQuery.error)}</div>
        ) : stockRanking ? (
          <StockRankingPanel data={stockRanking} />
        ) : (
          <div className="analysis-empty">目前沒有可顯示的選股排行資料。</div>
        )}
      </section>
    </main>
  );
}

function CorrelationHeatmap({ data }: { data: CorrelationResponse }) {
  return (
    <div className="heatmap-scroll">
      <div
        className="heatmap-grid"
        style={{
          gridTemplateColumns: `150px repeat(${data.symbols.length}, minmax(74px, 1fr))`
        }}
      >
        <div className="heatmap-corner" />
        {data.symbols.map((symbol) => (
          <div className="heatmap-col-header" key={symbol}>
            <span>{friendlyName(symbol)}</span>
          </div>
        ))}

        {data.symbols.map((rowSymbol, rowIndex) => (
          <Fragment key={rowSymbol}>
            <div className="heatmap-row-header" key={`${rowSymbol}-header`}>
              <strong>{friendlyName(rowSymbol)}</strong>
              <span>{rowSymbol}</span>
            </div>
            {data.symbols.map((colSymbol, colIndex) => {
              const value = data.matrix[rowIndex]?.[colIndex] ?? null;
              const diagonal = rowIndex === colIndex;
              return (
                <div
                  className={`heatmap-cell ${diagonal ? "diagonal" : colorClass(value)}`}
                  key={`${rowSymbol}-${colSymbol}`}
                  title={`${friendlyName(rowSymbol)} × ${friendlyName(colSymbol)}：${formatCorrelation(value)}（${periodLabel(data.period)}）`}
                >
                  {diagonal ? "—" : formatCorrelation(value)}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <div className="heatmap-meta">
        data points: {data.data_points} · calculated at {formatTime(data.calculated_at)}
      </div>
    </div>
  );
}

function HeatmapSkeleton({ count }: { count: number }) {
  return (
    <div className="heatmap-scroll">
      <div
        className="heatmap-grid"
        style={{
          gridTemplateColumns: `150px repeat(${count}, minmax(74px, 1fr))`
        }}
      >
        {Array.from({ length: (count + 1) * (count + 1) }).map((_, index) => (
          <div className="heatmap-skeleton-cell" key={index} />
        ))}
      </div>
    </div>
  );
}

function VolatilityRanking({ data }: { data: VolatilityResponse }) {
  const maxVolatility = Math.max(...data.items.map((item) => item.volatility_pct), 0.01);

  return (
    <div className="volatility-list">
      {data.items.map((item) => {
        const width = `${Math.max((item.volatility_pct / maxVolatility) * 100, 4)}%`;
        return (
          <div className="volatility-row" key={item.symbol}>
            <div className="volatility-label">
              <span>#{item.rank}</span>
              <strong>{friendlyName(item.symbol) || item.name}</strong>
              <em>{item.symbol}</em>
            </div>
            <div className="volatility-bar-track" title={`${item.name} volatility: ${formatPercent(item.volatility_pct)}`}>
              <div className={`volatility-bar ${volatilityClass(item.volatility_pct)}`} style={{ width }} />
              <strong>{formatPercent(item.volatility_pct)}</strong>
            </div>
            <div className="volatility-metrics">
              <span className={valueTone(item.period_return_pct)}>{formatSignedPercent(item.period_return_pct)}</span>
              <span className="drawdown">{formatPercent(item.max_drawdown_pct)}</span>
            </div>
          </div>
        );
      })}
      <div className="heatmap-meta">
        data points: {data.data_points} · calculated at {formatTime(data.calculated_at)}
      </div>
    </div>
  );
}

function VolatilitySkeleton() {
  return (
    <div className="volatility-list">
      {Array.from({ length: 8 }).map((_, index) => (
        <div className="volatility-skeleton-row" key={index}>
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

function SectorRotationPanel({ data }: { data: SectorRotationResponse }) {
  const relativeValues = data.items.map((item) => item.relative_return_pct);
  const momentumValues = data.items.map((item) => item.momentum_score);
  const minRelative = Math.min(...relativeValues, -1);
  const maxRelative = Math.max(...relativeValues, 1);
  const minMomentum = Math.min(...momentumValues, -0.01);
  const maxMomentum = Math.max(...momentumValues, 0.01);
  const maxVolatility = Math.max(...data.items.map((item) => item.volatility_pct), 1);

  return (
    <div className="sector-rotation-layout">
      <div className="bubble-chart" aria-label="板塊輪動泡泡圖">
        <div className="bubble-axis x-axis">Relative return</div>
        <div className="bubble-axis y-axis">Momentum</div>
        <div className="bubble-zero vertical" />
        <div className="bubble-zero horizontal" />
        {data.items.map((item) => {
          const left = scaleToPercent(item.relative_return_pct, minRelative, maxRelative);
          const top = 100 - scaleToPercent(item.momentum_score, minMomentum, maxMomentum);
          const size = 38 + (item.volatility_pct / maxVolatility) * 34;
          return (
            <div
              className={`sector-bubble ${rsClass(item.rs_score)}`}
              key={item.symbol}
              style={{
                left: `${left}%`,
                top: `${top}%`,
                width: `${size}px`,
                height: `${size}px`
              }}
              title={`${item.sector_name} ${item.symbol}
期間報酬：${formatSignedPercent(item.period_return_pct)}
相對報酬：${formatSignedPercent(item.relative_return_pct)}
Sharpe：${formatRatio(item.sharpe_ratio)}
波動率：${formatPercent(item.volatility_pct)}`}
            >
              <span>{item.sector_name}</span>
            </div>
          );
        })}
      </div>

      <div className="sector-table-wrap">
        <table className="sector-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>板塊</th>
              <th>RS</th>
              <th>Return</th>
              <th>Relative</th>
              <th>Sharpe</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <tr key={item.symbol}>
                <td>#{item.rank}</td>
                <td>
                  <strong>{item.sector_name}</strong>
                  <span>{item.symbol}</span>
                </td>
                <td>{formatRatio(item.rs_score)}</td>
                <td className={valueTone(item.period_return_pct)}>{formatSignedPercent(item.period_return_pct)}</td>
                <td className={valueTone(item.relative_return_pct)}>{formatSignedPercent(item.relative_return_pct)}</td>
                <td>{formatRatio(item.sharpe_ratio)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SectorRotationSkeleton() {
  return (
    <div className="sector-rotation-layout">
      <div className="bubble-chart skeleton-chart">
        {Array.from({ length: 11 }).map((_, index) => (
          <span key={index} />
        ))}
      </div>
      <div className="volatility-list">
        {Array.from({ length: 6 }).map((_, index) => (
          <div className="volatility-skeleton-row" key={index}>
            <span />
            <span />
            <span />
          </div>
        ))}
      </div>
    </div>
  );
}

function StockRankingPanel({ data }: { data: StockRankingResponse }) {
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const topThree = data.items.slice(0, 3);

  return (
    <div className="stock-ranking-layout">
      <div className="stock-ranking-table-wrap">
        <table className="stock-ranking-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>標的</th>
              <th>綜合</th>
              <th>動能</th>
              <th>低波動</th>
              <th>相對強弱</th>
              <th>趨勢</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <Fragment key={item.symbol}>
                <tr
                  className={item.rank === 1 ? "top-rank" : ""}
                  onClick={() => setExpandedSymbol((current) => (current === item.symbol ? null : item.symbol))}
                >
                  <td>#{item.rank}</td>
                  <td>
                    <strong>{item.name}</strong>
                    <span>{item.symbol}</span>
                  </td>
                  <td>
                    <strong className="composite-score">{formatScore(item.composite_score)}</strong>
                  </td>
                  <td><FactorBar value={item.momentum_score} /></td>
                  <td><FactorBar value={item.low_vol_score} /></td>
                  <td><FactorBar value={item.rs_score} /></td>
                  <td><FactorBar value={item.trend_score} /></td>
                </tr>
                {expandedSymbol === item.symbol ? (
                  <tr className="stock-detail-row">
                    <td colSpan={7}>
                      <div>
                        <span>期間報酬 {formatSignedPercent(item.period_return_pct)}</span>
                        <span>年化波動 {formatPercent(item.volatility_pct)}</span>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <RadarChart items={topThree} />
    </div>
  );
}

function FactorBar({ value }: { value: number }) {
  return (
    <div className="factor-bar">
      <div className={`factor-fill ${scoreClass(value)}`} style={{ width: `${Math.max(4, value)}%` }} />
      <span>{formatScore(value)}</span>
    </div>
  );
}

function RadarChart({ items }: { items: StockRankingItem[] }) {
  const axes = ["動能", "低波動", "相對強弱", "趨勢"];
  const colors = ["#00d4aa", "#38bdf8", "#facc15"];
  const center = 120;
  const radius = 82;
  const axisPoints = axes.map((_, index) => radarPoint(100, index, axes.length, center, radius));

  return (
    <div className="radar-panel">
      <svg viewBox="0 0 240 240" role="img" aria-label="前三名標的雷達圖">
        {[0.25, 0.5, 0.75, 1].map((level) => (
          <polygon
            className="radar-grid"
            key={level}
            points={axisPoints.map((_, index) => {
              const point = radarPoint(level * 100, index, axes.length, center, radius);
              return `${point.x},${point.y}`;
            }).join(" ")}
          />
        ))}
        {axisPoints.map((point, index) => (
          <line className="radar-axis" key={axes[index]} x1={center} y1={center} x2={point.x} y2={point.y} />
        ))}
        {axes.map((axis, index) => {
          const point = radarPoint(112, index, axes.length, center, radius);
          return (
            <text className="radar-label" key={axis} x={point.x} y={point.y}>
              {axis}
            </text>
          );
        })}
        {items.map((item, index) => {
          const values = [item.momentum_score, item.low_vol_score, item.rs_score, item.trend_score];
          const points = values.map((value, pointIndex) => {
            const point = radarPoint(value, pointIndex, values.length, center, radius);
            return `${point.x},${point.y}`;
          }).join(" ");
          return (
            <polygon
              className="radar-series"
              key={item.symbol}
              points={points}
              style={{ stroke: colors[index], fill: `${colors[index]}22` }}
            />
          );
        })}
      </svg>
      <div className="radar-legend">
        {items.map((item, index) => (
          <span key={item.symbol}>
            <i style={{ background: colors[index] }} />
            {item.name}
          </span>
        ))}
      </div>
    </div>
  );
}

function StockRankingSkeleton() {
  return (
    <div className="stock-ranking-layout">
      <div className="volatility-list">
        {Array.from({ length: 8 }).map((_, index) => (
          <div className="volatility-skeleton-row" key={index}>
            <span />
            <span />
            <span />
          </div>
        ))}
      </div>
      <div className="radar-panel skeleton-radar" />
    </div>
  );
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `${path} HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function friendlyName(symbol: string) {
  return symbolOptions.find((item) => item.symbol === symbol)?.name ?? symbol;
}

function colorClass(value: number | null) {
  if (value === null || Number.isNaN(value)) return "corr-neutral";
  if (value >= 0.7) return "corr-red-strong";
  if (value >= 0.4) return "corr-red";
  if (value >= 0.1) return "corr-gray";
  if (value >= -0.1) return "corr-zero";
  if (value > -0.4) return "corr-blue";
  return "corr-blue-strong";
}

function formatCorrelation(value: number | null) {
  if (value === null || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value.toFixed(2)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function volatilityClass(value: number) {
  if (value > 40) return "vol-high";
  if (value >= 20) return "vol-mid";
  return "vol-low";
}

function valueTone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}

function scoreClass(value: number) {
  if (value > 70) return "score-good";
  if (value >= 40) return "score-mid";
  return "score-bad";
}

function formatScore(value: number) {
  return Math.round(value).toString();
}

function radarPoint(value: number, index: number, total: number, center: number, radius: number) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  const scaled = (value / 100) * radius;
  return {
    x: center + Math.cos(angle) * scaled,
    y: center + Math.sin(angle) * scaled
  };
}

function rsClass(value: number) {
  if (value > 1.01) return "rs-strong";
  if (value < 0.99) return "rs-weak";
  return "rs-neutral";
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function scaleToPercent(value: number, min: number, max: number) {
  if (max === min) return 50;
  return Math.min(92, Math.max(8, ((value - min) / (max - min)) * 84 + 8));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function periodLabel(period: Period) {
  return periods.find((item) => item.value === period)?.label ?? period;
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "計算失敗";
}
