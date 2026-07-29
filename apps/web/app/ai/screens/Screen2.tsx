"use client";

import { useEffect, useState } from "react";
import { ElliottWaveCard } from "../../../components/ai/ElliottWaveCard";
import { InstitutionalFlow } from "../../../components/ai/InstitutionalFlow";
import { MarketChart } from "../../../components/ai/MarketChart";
import { TechnicalRanking } from "../../../components/ai/TechnicalRanking";
import { TechnicalSummaryTable } from "../../../components/ai/TechnicalSummaryTable";
import type { ElliottWaveData } from "../../../components/ai/elliottTypes";
import type { MarketScope } from "../types";

export interface Screen2Props {
  marketScope: MarketScope;
}

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

export function Screen2({ marketScope }: Screen2Props) {
  const [elliottData, setElliottData] = useState<ElliottWaveData | null>(null);
  const [elliottError, setElliottError] = useState<string | null>(null);
  const [elliottLoading, setElliottLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    async function loadElliottWave() {
      setElliottLoading(true);
      setElliottError(null);
      setElliottData(null);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/elliott-wave?scope=${marketScope}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as ElliottWaveData;
        setElliottData(payload);
      } catch (error) {
        if (controller.signal.aborted) return;
        setElliottError(error instanceof Error ? error.message : "elliott wave fetch failed");
      } finally {
        if (!controller.signal.aborted) setElliottLoading(false);
      }
    }

    void loadElliottWave();
    return () => controller.abort();
  }, [marketScope]);

  return (
    <div className="ai-screen-card ai-screen-card-wide ai-screen2-card">
      <div className="ai-screen2-header">
        <div>
          <span className="ai-screen-eyebrow">Screen 02</span>
          <h1>第二屏：支撐數據</h1>
          <p>以大盤 K 線、技術狀態、Watchlist 排行與法人動向，作為 AI 摘要的量化支撐層。</p>
        </div>
        <InstitutionalFlow marketScope={marketScope} />
      </div>

      <div className="ai-screen2-layout">
        <section className="ai-screen2-chart-stack" aria-label="大盤 K 線與波浪理論">
          <MarketChart marketScope={marketScope} elliottData={elliottData} />
          <ElliottWaveCard data={elliottData} error={elliottError} loading={elliottLoading} marketScope={marketScope} />
        </section>

        <aside className="ai-screen2-side" aria-label="技術與法人摘要">
          <TechnicalSummaryTable marketScope={marketScope} />
          <TechnicalRanking marketScope={marketScope} />
        </aside>
      </div>
    </div>
  );
}
