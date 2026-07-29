"use client";

import { useEffect, useState } from "react";

export interface TechnicalRankingProps {
  marketScope: "tw" | "us";
}

type RankingItem = {
  rank: number;
  name: string;
  symbol: string;
  score: number;
  signals: string[];
  direction: "bullish" | "bearish" | "neutral";
};

type RankingResponse = {
  updated_at: string;
  rankings: RankingItem[];
};

type LoadState = {
  data: RankingResponse | null;
  error: string | null;
  loading: boolean;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const trendSymbol = {
  bullish: "↑",
  bearish: "↓",
  neutral: "→",
};

const trendColor = {
  bullish: "var(--positive)",
  bearish: "var(--negative)",
  neutral: "var(--muted)",
};

export function TechnicalRanking({ marketScope }: TechnicalRankingProps) {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });

  useEffect(() => {
    const controller = new AbortController();

    async function loadRanking() {
      setState({ data: null, error: null, loading: true });
      try {
        const market = marketScope === "us" ? "US" : "TAIEX";
        const response = await fetch(`${apiBaseUrl}/api/v1/technical/ranking?market=${market}&limit=5`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as RankingResponse;
        setState({ data: payload, error: null, loading: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          error: error instanceof Error ? error.message : "technical ranking fetch failed",
          loading: false,
        });
      }
    }

    void loadRanking();
    return () => controller.abort();
  }, [marketScope]);

  const rankings = state.data?.rankings ?? [];

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
          <span style={{ color: "var(--muted-2)", fontSize: "var(--text-xs)", fontWeight: 800 }}>RANKING</span>
          <h2 style={{ color: "var(--text)", fontSize: 16, margin: "4px 0 0" }}>技術評分前 5 名</h2>
        </div>
        <strong style={{ color: "var(--muted)", fontSize: "var(--text-xs)" }}>
          {state.data?.updated_at ?? marketScope.toUpperCase()}
        </strong>
      </div>

      {state.loading ? (
        <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)", padding: 14 }}>載入中...</div>
      ) : null}
      {state.error ? (
        <div style={{ color: "var(--negative)", fontSize: "var(--text-sm)", padding: 14 }}>資料載入失敗，請稍後再試</div>
      ) : null}
      {!state.loading && !state.error && rankings.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)", padding: 14 }}>資料暫缺</div>
      ) : null}
      {!state.loading && !state.error && rankings.length > 0 ? (
        <div style={{ display: "grid" }}>
          {rankings.map((item) => (
            <div
              key={item.symbol}
              title={item.signals.join(" / ")}
              style={{
                display: "grid",
                gridTemplateColumns: "34px 1fr 68px 48px",
                gap: 10,
                alignItems: "center",
                borderTop: item.rank === 1 ? "none" : "1px solid var(--border-soft)",
                padding: "12px 14px",
              }}
            >
              <strong style={{ color: item.rank === 1 ? "var(--accent)" : "var(--muted)", fontSize: "var(--text-sm)" }}>
                #{item.rank}
              </strong>
              <div style={{ minWidth: 0 }}>
                <strong style={{ color: "var(--text)", display: "block", fontSize: "var(--text-sm)" }}>{item.name}</strong>
                <span style={{ color: "var(--muted-2)", fontSize: "var(--text-xs)" }}>{item.symbol}</span>
              </div>
              <div style={{ display: "grid", gap: 5 }}>
                <strong style={{ color: "var(--text)", fontSize: "var(--text-sm)", textAlign: "right" }}>{item.score}</strong>
                <div style={{ height: 5, overflow: "hidden", borderRadius: 999, background: "var(--border-soft)" }}>
                  <span
                    style={{
                      display: "block",
                      width: `${item.score}%`,
                      height: "100%",
                      background: item.score >= 75 ? "var(--positive)" : item.score >= 60 ? "var(--warning)" : "var(--negative)",
                    }}
                  />
                </div>
              </div>
              <span style={{ color: trendColor[item.direction], fontSize: 22, fontWeight: 900, textAlign: "right" }}>
                {trendSymbol[item.direction]}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
