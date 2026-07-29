"use client";

import { useMemo, useState } from "react";
import type { AiMarketPageData, MarketDirection, MarketScope } from "../types";

type ProviderStatus = "ok" | "error" | "pending" | "not_configured";
type AiDirection = "bullish" | "bearish" | "neutral";
type ConsensusStatus = "full" | "partial" | "unavailable";
type ProviderKey = "all" | "openai" | "perplexity" | "gemini" | "claude";

type ProviderResult = {
  provider?: string;
  status: ProviderStatus;
  direction: AiDirection | null;
  summary: string | null;
  key_points: string[];
  error: string | null;
};

type AiBriefResponse = {
  scope: MarketScope;
  date: string;
  openai: ProviderResult;
  perplexity: ProviderResult;
  gemini: ProviderResult;
  claude: ProviderResult;
  consensus: {
    status: ConsensusStatus;
    score: number;
    direction: AiDirection | null;
  };
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const disclaimer = "本摘要由 AI 自動生成，僅供參考，不構成任何投資建議。";

const directionClass: Record<MarketDirection | AiDirection, string> = {
  bullish: "positive",
  bearish: "negative",
  neutral: "neutral",
  sideways: "neutral",
};

const directionLabel: Record<AiDirection, string> = {
  bullish: "多方",
  bearish: "空方",
  neutral: "震盪",
};

const providerTabs: Array<{ id: ProviderKey; label: string; disabled?: boolean }> = [
  { id: "all", label: "All AI" },
  { id: "openai", label: "ChatGPT" },
  { id: "perplexity", label: "Perplexity" },
  { id: "gemini", label: "Gemini" },
  { id: "claude", label: "Claude", disabled: true },
];

function formatPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function providerTitle(provider: ProviderKey) {
  if (provider === "openai") return "ChatGPT";
  if (provider === "perplexity") return "Perplexity";
  if (provider === "gemini") return "Gemini";
  if (provider === "claude") return "Claude";
  return "All AI";
}

function statusLabel(status: ProviderStatus) {
  if (status === "ok") return "完成";
  if (status === "error") return "錯誤";
  if (status === "not_configured") return "未設定";
  return "預留";
}

function aiProviderResults(response: AiBriefResponse) {
  return [response.openai, response.perplexity, response.gemini];
}

type ConsensusView = {
  score: number;
  status: "mock" | ConsensusStatus;
  direction: AiDirection;
  summary: string;
  keyPoints: string[];
};

function summarizeConsensus(response: AiBriefResponse | null, fallback: AiMarketPageData): ConsensusView {
  if (!response) {
    const brief = fallback.aiBriefs.find((item) => item.provider === "all");
    return {
      score: brief?.confidence ?? 0,
      status: "mock",
      direction: fallback.marketSummary.direction === "sideways" ? "neutral" : fallback.marketSummary.direction,
      summary: brief?.content ?? fallback.marketSummary.summary,
      keyPoints: fallback.rankings.slice(0, 3).map((item) => `${item.name}：${item.reason}`),
    };
  }

  const okResults = aiProviderResults(response).filter((item) => item.status === "ok");
  const okSummaries = okResults
    .filter((item) => item.status === "ok" && item.summary)
    .map((item) => item.summary as string);

  return {
    score: response.consensus.score,
    status: response.consensus.status,
    direction: response.consensus.direction ?? "neutral",
    summary: okSummaries[0] ?? "目前 AI provider 尚未產生可用摘要，請確認 API key 設定後再試。",
    keyPoints: okResults.flatMap((item) =>
      item.status === "ok" ? item.key_points : []
    ).slice(0, 3),
  };
}

function ProviderPanel({
  provider,
  response,
  fallback,
}: {
  provider: ProviderKey;
  response: AiBriefResponse | null;
  fallback: AiMarketPageData;
}) {
  if (provider === "all") {
    const consensus = summarizeConsensus(response, fallback);
    return (
      <div className="ai-provider-panel">
        <div className="ai-consensus-header">
          <span>共識指數</span>
          <strong>{consensus.score}%</strong>
        </div>
        <div className="ai-consensus-track" aria-label={`共識指數 ${consensus.score}%`}>
          <span style={{ width: `${Math.max(0, Math.min(consensus.score, 100))}%` }} />
        </div>
        <div className="ai-consensus-meta">
          <em className={directionClass[consensus.direction]}>{directionLabel[consensus.direction]}</em>
          <small>{consensus.status === "mock" ? "Mock 預覽" : `Consensus ${consensus.status}`}</small>
        </div>
        <p>{consensus.summary}</p>
        <ul className="ai-key-points">
          {consensus.keyPoints.length > 0 ? (
            consensus.keyPoints.map((point) => <li key={point}>{point}</li>)
          ) : (
            <li>暫無關鍵重點。</li>
          )}
        </ul>
      </div>
    );
  }

  const result = response?.[provider];
  const fallbackBrief = fallback.aiBriefs.find((item) => {
    if (provider === "openai") return item.provider === "chatgpt";
    return item.provider === provider;
  });

  if (!result) {
    return (
      <div className="ai-provider-panel muted">
        <strong>{providerTitle(provider)}</strong>
        <p>{fallbackBrief?.content ?? "尚未產生摘要。"}</p>
      </div>
    );
  }

  return (
    <div className="ai-provider-panel">
      <div className="ai-provider-state">
        <strong>{providerTitle(provider)}</strong>
        <span className={`ai-provider-badge ${result.status}`}>{statusLabel(result.status)}</span>
      </div>
      {result.status === "ok" ? (
        <>
          <em className={`ai-provider-direction ${directionClass[result.direction ?? "neutral"]}`}>
            {directionLabel[result.direction ?? "neutral"]}
          </em>
          <p>{result.summary}</p>
          <ul className="ai-key-points">
            {result.key_points.map((point) => <li key={point}>{point}</li>)}
          </ul>
        </>
      ) : result.status === "error" ? (
        <p className="ai-provider-error">{result.error ?? "Provider 暫時無法使用。"}</p>
      ) : result.status === "not_configured" ? (
        <p className="ai-provider-not-configured">此 provider 尚未設定 API key。</p>
      ) : (
        <p>此 provider 已保留，尚未啟用。</p>
      )}
    </div>
  );
}

export function Screen1({ data, marketScope }: { data: AiMarketPageData; marketScope: MarketScope }) {
  const [activeTab, setActiveTab] = useState<ProviderKey>("all");
  const [brief, setBrief] = useState<AiBriefResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const direction = useMemo(() => {
    const aiDirection = brief?.consensus.direction;
    if (aiDirection) return aiDirection;
    return data.marketSummary.direction;
  }, [brief, data.marketSummary.direction]);

  async function generateBrief() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/ai/brief`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: marketScope }),
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as AiBriefResponse;
      setBrief(payload);
      setActiveTab("all");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "AI 摘要產生失敗");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ai-screen-card ai-screen-card-wide ai-brief-dashboard">
      <div className="ai-screen-heading-row">
        <div>
          <span className="ai-screen-eyebrow">Screen 01</span>
          <h1>第一屏：AI 摘要</h1>
          <p>{data.marketSummary.title} · {data.marketSummary.primaryIndex}</p>
        </div>
        <strong className={`ai-direction ${directionClass[direction]}`}>
          {direction === "sideways" ? data.marketSummary.directionLabel : directionLabel[direction]}
        </strong>
      </div>

      <div className="ai-metric-strip">
        <div>
          <span>今日漲跌</span>
          <strong className={data.marketSummary.changePct && data.marketSummary.changePct < 0 ? "negative" : "positive"}>
            {formatPercent(data.marketSummary.changePct)}
          </strong>
        </div>
        <div>
          <span>量能</span>
          <strong>{data.marketSummary.turnoverLabel ?? "-"}</strong>
        </div>
        <div>
          <span>摘要日期</span>
          <strong>{brief?.date ?? "尚未產生"}</strong>
        </div>
      </div>

      <div className="ai-brief-toolbar">
        <div className="ai-provider-tabs" role="tablist" aria-label="AI providers">
          {providerTabs.map((tab) => (
            <button
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "active" : ""}
              disabled={tab.disabled}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              type="button"
            >
              {tab.label}
              {tab.disabled ? <small>預留</small> : null}
            </button>
          ))}
        </div>
        <button className="ai-generate-button" disabled={loading} onClick={generateBrief} type="button">
          {loading ? "產生中..." : "產生摘要"}
        </button>
      </div>

      {error ? <div className="ai-brief-error">資料載入失敗，請稍後再試：{error}</div> : null}
      <ProviderPanel provider={activeTab} response={brief} fallback={data} />

      <section className="ai-ranking-preview" aria-label="Watchlist 今日前 3 名">
        {data.rankings.slice(0, 3).map((item, index) => (
          <article key={item.symbol}>
            <span>#{index + 1}</span>
            <strong>{item.name}</strong>
            <small className="ai-ranking-reason">
              {item.symbol} · {item.reason?.trim() ? item.reason : "-"}
            </small>
          </article>
        ))}
      </section>

      <aside className="ai-brief-disclaimer">{disclaimer}</aside>
    </div>
  );
}
