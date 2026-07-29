"use client";

import { useEffect, useState } from "react";

export interface InstitutionalFlowProps {
  marketScope: "tw" | "us";
}

type FlowItem = {
  buy: number;
  sell: number;
  net: number;
};

type InstitutionalResponse = {
  updated_at: string | null;
  source: string;
  data: {
    foreign: FlowItem;
    trust: FlowItem;
    dealer: FlowItem;
  };
  summary: string;
  error_message?: string | null;
};

type LoadState = {
  data: InstitutionalResponse | null;
  error: string | null;
  loading: boolean;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

function formatNet(value: number) {
  const amount = value / 100_000_000;
  const sign = amount > 0 ? "+" : "";
  return `${sign}${amount.toFixed(1)}億`;
}

function FlowChip({ label, value }: { label: string; value: number }) {
  const isPositive = value >= 0;
  return (
    <span className={`ai-institutional-chip ${isPositive ? "is-positive" : "is-negative"}`}>
      <strong>{label}</strong>
      <span>{formatNet(value)}</span>
      <em aria-hidden="true">{isPositive ? "↑" : "↓"}</em>
    </span>
  );
}

export function InstitutionalFlow({ marketScope }: InstitutionalFlowProps) {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });

  useEffect(() => {
    const controller = new AbortController();

    async function loadFlow() {
      setState({ data: null, error: null, loading: true });
      try {
        if (marketScope === "us") {
          throw new Error("美股法人資料即將支援");
        }
        const response = await fetch(`${apiBaseUrl}/api/v1/institutional/flow?market=TAIEX`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as InstitutionalResponse;
        setState({ data: payload, error: null, loading: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          error: error instanceof Error ? error.message : "institutional flow fetch failed",
          loading: false,
        });
      }
    }

    void loadFlow();
    return () => controller.abort();
  }, [marketScope]);

  return (
    <section className="ai-institutional-inline" aria-label="三大法人動向">
      <div className="ai-institutional-inline-header">
        <div>
          <span>FLOW</span>
          <h2>三大法人</h2>
        </div>
        <strong>{state.data?.updated_at ?? "—"}</strong>
      </div>

      {state.loading ? <p className="ai-institutional-muted">載入中...</p> : null}
      {state.error ? <p className="ai-institutional-muted">資料暫缺</p> : null}
      {!state.loading && !state.error && state.data ? (
        <>
          <div className="ai-institutional-chip-row">
            <FlowChip label="外資" value={state.data.data.foreign.net} />
            <FlowChip label="投信" value={state.data.data.trust.net} />
            <FlowChip label="自營" value={state.data.data.dealer.net} />
          </div>
          {state.data.error_message ? (
            <p className="ai-institutional-warning" title={state.data.error_message}>
              ⚠ {state.data.error_message}
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
