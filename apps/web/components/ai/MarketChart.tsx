"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  LineStyle,
  createSeriesMarkers,
  createChart,
  type BusinessDay,
  type CandlestickData,
  type IChartApi,
  type SeriesMarker,
} from "lightweight-charts";
import type { ElliottWaveData } from "./elliottTypes";

export interface MarketChartProps {
  marketScope: "tw" | "us";
  elliottData?: ElliottWaveData | null;
}

type ChartRange = "1D" | "1W" | "1M";

type ChartRequest = {
  interval: "1d" | "1wk" | "1mo";
  range: "3mo" | "1y" | "5y";
};

type ApiCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

type CandleResponse = ApiCandle[] | { candles?: ApiCandle[]; data?: ApiCandle[] };

type LoadState = {
  candles: ApiCandle[];
  error: string | null;
  loading: boolean;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const ranges: ChartRange[] = ["1D", "1W", "1M"];

const requestByRange: Record<ChartRange, ChartRequest> = {
  "1D": { interval: "1d", range: "5y" },
  "1W": { interval: "1wk", range: "1y" },
  "1M": { interval: "1mo", range: "1y" },
};

const baseColors: Record<string, string> = {
  C1: "#ef4444",
  C2: "#f97316",
  C3: "#eab308",
};

function normalizeCandles(payload: CandleResponse): ApiCandle[] {
  const candles = Array.isArray(payload) ? payload : payload.candles ?? payload.data ?? [];
  const byTime = new Map<string, ApiCandle>();

  candles
    .filter(
      (item) =>
        /^\d{4}-\d{2}-\d{2}$/.test(item.time) &&
        Number.isFinite(item.open) &&
        Number.isFinite(item.high) &&
        Number.isFinite(item.low) &&
        Number.isFinite(item.close),
    )
    .forEach((item) => {
      byTime.set(item.time, item);
    });

  return Array.from(byTime.values()).sort((a, b) => a.time.localeCompare(b.time));
}

function toBusinessDay(value: string): BusinessDay {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function toChartData(candles: ApiCandle[]): CandlestickData<BusinessDay>[] {
  return candles.map((item) => ({
    time: toBusinessDay(item.time),
    open: item.open,
    high: item.high,
    low: item.low,
    close: item.close,
  }));
}

function findMarkerTime(candles: ApiCandle[], targetDate: string): BusinessDay | null {
  const candle = candles.find((item) => item.time >= targetDate) ?? null;
  return candle ? toBusinessDay(candle.time) : null;
}

function getChartColors() {
  if (typeof window === "undefined") {
    return {
      background: "#111827",
      border: "#263244",
      down: "#ef4444",
      grid: "#1f2937",
      text: "#94a3b8",
      up: "#00d4aa",
    };
  }

  const style = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    background: read("--chart-bg", "#111827"),
    border: read("--chart-border", "#263244"),
    down: read("--chart-down", "#ef4444"),
    grid: read("--chart-grid", "#1f2937"),
    text: read("--chart-text", "#94a3b8"),
    up: read("--chart-up", "#00d4aa"),
  };
}

function MarketChartSkeleton() {
  return (
    <div style={{ display: "grid", gap: 10, padding: 16 }}>
      {[64, 92, 78, 56].map((width, index) => (
        <div
          key={index}
          style={{
            width: `${width}%`,
            height: index === 1 ? 180 : 14,
            borderRadius: 10,
            background: "linear-gradient(90deg, var(--panel-2), var(--border-soft), var(--panel-2))",
          }}
        />
      ))}
    </div>
  );
}

function MarketChartPlaceholder({ children }: { children: string }) {
  return (
    <div
      style={{
        display: "grid",
        minHeight: 360,
        placeItems: "center",
        border: "1px solid var(--border-soft)",
        borderRadius: 12,
        background: "var(--panel)",
        color: "var(--muted)",
        fontSize: "var(--text-sm)",
        padding: 20,
      }}
    >
      {children}
    </div>
  );
}

function trendTone(trend: ElliottWaveData["trend"] | undefined) {
  if (trend === "bullish") return "var(--positive)";
  if (trend === "bearish") return "var(--negative)";
  return "var(--muted)";
}

export function MarketChart({ marketScope, elliottData }: MarketChartProps) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [range, setRange] = useState<ChartRange>("1D");
  const [state, setState] = useState<LoadState>({ candles: [], error: null, loading: false });

  const requestUrl = useMemo(() => {
    const request = requestByRange[range];
    const params = new URLSearchParams({
      symbol: "^TWII",
      interval: request.interval,
      range: request.range,
    });
    return `${apiBaseUrl}/api/v1/market/candles?${params.toString()}`;
  }, [range]);

  useEffect(() => {
    if (marketScope === "us") return;
    const controller = new AbortController();

    async function loadCandles() {
      setState((current) => ({ ...current, error: null, loading: true }));
      try {
        const response = await fetch(requestUrl, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as CandleResponse;
        const candles = normalizeCandles(payload);
        setState({ candles, error: null, loading: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          candles: [],
          error: error instanceof Error ? error.message : "market chart fetch failed",
          loading: false,
        });
      }
    }

    void loadCandles();
    return () => controller.abort();
  }, [marketScope, requestUrl]);

  useEffect(() => {
    if (marketScope === "us" || state.loading || state.error || state.candles.length === 0) return;
    if (!chartContainerRef.current) return;

    chartRef.current?.remove();
    chartRef.current = null;

    let chart: IChartApi | null = null;
    const frame = requestAnimationFrame(() => {
      const container = chartContainerRef.current;
      if (!container) return;

      console.log("container size:", container.offsetWidth, container.offsetHeight);
      if (container.offsetWidth === 0 || container.offsetHeight === 0) {
        console.warn("MarketChart container has zero size; skip chart creation.");
        return;
      }

      const colors = getChartColors();
      chart = createChart(container, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: colors.background },
          textColor: colors.text,
        },
        grid: {
          vertLines: { color: colors.grid },
          horzLines: { color: colors.grid },
        },
        rightPriceScale: {
          borderColor: colors.border,
        },
        timeScale: {
          borderColor: colors.border,
          timeVisible: false,
          secondsVisible: false,
        },
      });

      chartRef.current = chart;
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: colors.up,
        downColor: colors.down,
        borderUpColor: colors.up,
        borderDownColor: colors.down,
        wickUpColor: colors.up,
        wickDownColor: colors.down,
      });

      const chartData = toChartData(state.candles);
      candleSeries.setData(chartData);
      if (elliottData) {
        const markers = elliottData.all_bases.reduce<SeriesMarker<BusinessDay>[]>((items, base) => {
            const time = findMarkerTime(state.candles, base.date);
            if (!time) return items;
            items.push({
              time,
              position: "belowBar" as const,
              color: baseColors[base.id] ?? "#94a3b8",
              shape: "arrowUp" as const,
              text: `${base.id} ${base.label}`,
              size: base.id === elliottData.base_id ? 2 : 1,
            });
            return items;
          }, []);
        if (markers.length) createSeriesMarkers(candleSeries, markers);

        candleSeries.createPriceLine({
          price: elliottData.support,
          color: "#22c55e",
          lineStyle: LineStyle.Dashed,
          lineWidth: 1,
          title: `支撐 ${Math.round(elliottData.support)}`,
        });
        candleSeries.createPriceLine({
          price: elliottData.resistance,
          color: "#ef4444",
          lineStyle: LineStyle.Dashed,
          lineWidth: 1,
          title: `壓力 ${Math.round(elliottData.resistance)}`,
        });
      }
      chart.timeScale().fitContent();
    });

    return () => {
      cancelAnimationFrame(frame);
      if (chart) {
        chart.remove();
      } else {
        chartRef.current?.remove();
      }
      chartRef.current = null;
    };
  }, [elliottData, marketScope, state.candles, state.error, state.loading]);

  if (marketScope === "us") {
    return <MarketChartPlaceholder>美股大盤 K 線即將支援</MarketChartPlaceholder>;
  }

  return (
    <section
      style={{
        display: "grid",
        gap: 12,
        border: "1px solid var(--border-soft)",
        borderRadius: 12,
        background: "var(--panel)",
        padding: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <span style={{ color: "var(--muted-2)", fontSize: "var(--text-xs)", fontWeight: 800 }}>^TWII</span>
          <h2 style={{ color: "var(--text)", fontSize: 18, margin: "4px 0 0" }}>台灣加權指數 K 線</h2>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {ranges.map((item) => (
            <button
              key={item}
              onClick={() => setRange(item)}
              style={{
                border: "1px solid var(--border-soft)",
                borderRadius: 8,
                background: item === range ? "var(--accent)" : "var(--panel-2)",
                color: item === range ? "#001b18" : "var(--muted)",
                cursor: "pointer",
                fontSize: "var(--text-xs)",
                fontWeight: 800,
                padding: "7px 10px",
              }}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {state.loading ? <MarketChartSkeleton /> : null}
      {state.error ? <MarketChartPlaceholder>資料載入失敗，請稍後再試</MarketChartPlaceholder> : null}
      {!state.loading && !state.error && state.candles.length === 0 ? (
        <MarketChartPlaceholder>目前沒有 K 線資料</MarketChartPlaceholder>
      ) : null}
      {!state.loading && !state.error && state.candles.length > 0 ? (
        <div style={{ position: "relative" }}>
          {elliottData ? (
            <div className="ai-chart-wave-badge" style={{ color: trendTone(elliottData.trend) }}>
              {elliottData.wave_label}
            </div>
          ) : null}
          <div ref={chartContainerRef} style={{ height: 360, minHeight: 360 }} />
        </div>
      ) : null}
    </section>
  );
}
