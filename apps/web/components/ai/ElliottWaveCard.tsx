"use client";

import type { ElliottTrend, ElliottWaveData } from "./elliottTypes";

export interface ElliottWaveCardProps {
  data: ElliottWaveData | null;
  error?: string | null;
  loading?: boolean;
  marketScope: "tw" | "us";
}

function ElliottWaveSkeleton() {
  return (
    <div className="ai-wave-skeleton">
      <span />
      <span />
      <span />
    </div>
  );
}

function formatNumber(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 }).format(value);
}

function trendLabel(trend: ElliottTrend | string | undefined) {
  if (trend === "bullish") return "偏多";
  if (trend === "bearish") return "偏空";
  return "中性";
}

export function ElliottWaveCard({ data, error, loading, marketScope }: ElliottWaveCardProps) {
  const selectedBase = data?.all_bases.find((base) => base.id === data.base_id);

  return (
    <section className="ai-wave-card">
      {data?.source === "fallback" ? (
        <div className="ai-wave-warning">⚠ Gemini 暫無回應，顯示近期快取資料</div>
      ) : null}

      <div className="ai-wave-card-header">
        <div>
          <span>WAVE</span>
          <h2>波浪理論分析</h2>
        </div>
        {data ? <strong className={`ai-wave-trend is-${data.trend}`}>{trendLabel(data.trend)}</strong> : <strong>{marketScope.toUpperCase()}</strong>}
      </div>

      {loading ? <ElliottWaveSkeleton /> : null}
      {error ? <p className="ai-wave-muted">分析暫時無法使用</p> : null}
      {!loading && !error && !data ? <p className="ai-wave-muted">波浪資料暫缺</p> : null}

      {!loading && !error && data ? (
        <div className="ai-wave-structured">
          <div className="ai-wave-block">
            <span>📍 起算基底</span>
            <strong>
              {data.base_id} {selectedBase?.label ?? ""}
            </strong>
            <small>
              {data.base_date} / {formatNumber(data.base_price)} 點
            </small>
            <p>{data.base_reason}</p>
          </div>

          <div className="ai-wave-row">
            <span>🌊 目前位置</span>
            <strong>{data.wave_label}</strong>
          </div>

          <div className="ai-wave-levels">
            <span className="is-support">🟢 支撐：{formatNumber(data.support)}</span>
            <span className="is-resistance">🔴 壓力：{formatNumber(data.resistance)}</span>
          </div>

          <p className="ai-wave-note">💡 {data.note}</p>
        </div>
      ) : null}

      {data ? (
        <footer>
          <span>{data.generated_at}</span>
          <span>來源：{data.source === "gemini" ? "Gemini" : "Fallback"}</span>
        </footer>
      ) : null}
    </section>
  );
}
