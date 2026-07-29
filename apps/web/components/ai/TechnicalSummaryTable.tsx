"use client";

import { useEffect, useMemo, useState } from "react";

export interface TechnicalSummaryTableProps {
  marketScope: "tw" | "us";
}

type TechnicalSignals = {
  rsi: "overbought" | "oversold" | "neutral";
  macd: "bullish" | "bearish";
  kd: "bullish" | "bearish" | "neutral";
};

type TechnicalSummaryResponse = {
  symbol: string;
  updated_at: string;
  indicators: {
    RSI: { value: number | null; signal: TechnicalSignals["rsi"] };
    MACD: { value: number | null; signal: TechnicalSignals["macd"] };
    KD: { k: number | null; d: number | null; signal: TechnicalSignals["kd"] };
    MA20: { value: number | null; signal: "bullish" | "bearish" | "neutral" };
    MA60: { value: number | null; signal: "bullish" | "bearish" | "neutral" };
  };
  overall: "bullish" | "bearish" | "neutral";
};

type LoadState = {
  data: TechnicalSummaryResponse | null;
  error: string | null;
  loading: boolean;
};

type Tone = "positive" | "negative" | "neutral";

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const signalLabel = {
  rsi: {
    overbought: { label: "超買", tone: "negative" as Tone, message: "動能偏熱，留意拉回" },
    oversold: { label: "超賣", tone: "positive" as Tone, message: "動能偏冷，留意反彈" },
    neutral: { label: "中性", tone: "neutral" as Tone, message: "位於常態區間" },
  },
  macd: {
    bullish: { label: "多頭", tone: "positive" as Tone, message: "MACD 位於零軸上方" },
    bearish: { label: "空頭", tone: "negative" as Tone, message: "MACD 位於零軸下方" },
  },
  kd: {
    bullish: { label: "金叉", tone: "positive" as Tone, message: "K 值高於 D 值" },
    bearish: { label: "死叉", tone: "negative" as Tone, message: "K 值低於 D 值" },
    neutral: { label: "中性", tone: "neutral" as Tone, message: "K/D 尚未形成方向" },
  },
};

const toneColor: Record<Tone, string> = {
  positive: "var(--positive)",
  negative: "var(--negative)",
  neutral: "var(--muted)",
};

function formatValue(value: number | null) {
  if (value === null || Number.isNaN(value)) return "資料暫缺";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function SkeletonRows() {
  return (
    <div style={{ display: "grid", gap: 10, padding: 14 }}>
      {[0, 1, 2].map((item) => (
        <div
          key={item}
          style={{
            height: 34,
            borderRadius: 8,
            background: "linear-gradient(90deg, var(--panel-2), var(--border-soft), var(--panel-2))",
          }}
        />
      ))}
    </div>
  );
}

function ErrorState() {
  return (
    <div style={{ color: "var(--negative)", fontSize: "var(--text-sm)", padding: 14 }}>
      資料載入失敗，請稍後再試
    </div>
  );
}

export function TechnicalSummaryTable({ marketScope }: TechnicalSummaryTableProps) {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });

  useEffect(() => {
    const controller = new AbortController();

    async function loadTechnicalSummary() {
      setState({ data: null, error: null, loading: true });
      try {
        const symbol = marketScope === "us" ? "^GSPC" : "^TWII";
        const response = await fetch(`${apiBaseUrl}/api/v1/technical/summary?symbol=${encodeURIComponent(symbol)}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as TechnicalSummaryResponse;
        setState({ data: payload, error: null, loading: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          error: error instanceof Error ? error.message : "technical summary fetch failed",
          loading: false,
        });
      }
    }

    void loadTechnicalSummary();
    return () => controller.abort();
  }, [marketScope]);

  const rows = useMemo(() => {
    if (!state.data) return [];
    const indicators = state.data.indicators;
    const rsiStatus = signalLabel.rsi[indicators.RSI.signal];
    const macdStatus = signalLabel.macd[indicators.MACD.signal];
    const kdStatus = signalLabel.kd[indicators.KD.signal];
    return [
      {
        name: "RSI",
        value: formatValue(indicators.RSI.value),
        status: rsiStatus,
      },
      {
        name: "MACD",
        value: formatValue(indicators.MACD.value),
        status: macdStatus,
      },
      {
        name: "KD",
        value:
          indicators.KD.k === null || indicators.KD.d === null
            ? "資料暫缺"
            : `K ${formatValue(indicators.KD.k)} / D ${formatValue(indicators.KD.d)}`,
        status: kdStatus,
      },
    ];
  }, [state.data]);

  return (
    <section
      style={{
        border: "1px solid var(--border-soft)",
        borderRadius: 12,
        background: "var(--panel)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border-soft)",
          padding: "12px 14px",
        }}
      >
        <div>
          <span style={{ color: "var(--muted-2)", fontSize: "var(--text-xs)", fontWeight: 800 }}>TECHNICAL</span>
          <h2 style={{ color: "var(--text)", fontSize: 16, margin: "4px 0 0" }}>技術狀態摘要</h2>
        </div>
        <strong style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>{marketScope.toUpperCase()}</strong>
      </div>

      {state.loading ? <SkeletonRows /> : null}
      {state.error ? <ErrorState /> : null}
      {!state.loading && !state.error && state.data ? (
        <div style={{ display: "grid" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "0.8fr 1fr 0.9fr 1.4fr",
              gap: 10,
              color: "var(--muted-2)",
              fontSize: "var(--text-xs)",
              fontWeight: 800,
              padding: "10px 14px",
            }}
          >
            <span>指標名稱</span>
            <span>數值</span>
            <span>狀態標籤</span>
            <span>訊號</span>
          </div>
          {rows.map((row) => (
            <div
              key={row.name}
              style={{
                display: "grid",
                gridTemplateColumns: "0.8fr 1fr 0.9fr 1.4fr",
                gap: 10,
                alignItems: "center",
                borderTop: "1px solid var(--border-soft)",
                color: "var(--text)",
                fontSize: "var(--text-sm)",
                padding: "12px 14px",
              }}
            >
              <strong>{row.name}</strong>
              <span>{row.value}</span>
              <span
                style={{
                  width: "fit-content",
                  border: "1px solid var(--border-soft)",
                  borderRadius: 999,
                  color: toneColor[row.status.tone],
                  fontSize: "var(--text-xs)",
                  fontWeight: 800,
                  padding: "4px 8px",
                }}
              >
                {row.status.label}
              </span>
              <span style={{ color: "var(--muted)" }}>{row.status.message}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
