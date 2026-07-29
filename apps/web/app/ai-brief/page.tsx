"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, ChevronDown, ChevronUp, Clock3, Loader2, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type ApiResponse<T> = {
  data: T;
  meta: Record<string, unknown>;
  timestamp: string;
};

type MarketBrief = {
  id: string;
  brief_text: string;
  data_snapshot: MarketSnapshot;
  model: string;
  tokens_used: number | null;
  created_at: string;
  generated_at?: string;
};

type MarketSnapshot = {
  watchlist?: Array<{
    symbol: string;
    name: string;
    latest_close: number | null;
    one_day_change_pct: number | null;
    five_day_change_pct: number | null;
  }>;
  sector_rotation?: {
    benchmark?: string;
    benchmark_return_pct?: number | null;
    top?: Array<{
      symbol: string;
      sector_name: string;
      rank: number;
      rs_score: number;
      relative_return_pct: number;
    }>;
  };
  stock_ranking_top3?: Array<{
    symbol: string;
    name: string;
    rank: number;
    composite_score: number;
    period_return_pct: number;
  }>;
  vix?: {
    latest: number | null;
    five_day_average: number | null;
  };
  disclaimer?: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";
const disclaimer = "⚠️ 本摘要由 AI 自動生成，僅供參考，不構成任何投資建議。";

export default function AiBriefPage() {
  const queryClient = useQueryClient();
  const [activeBrief, setActiveBrief] = useState<MarketBrief | null>(null);
  const [displayedText, setDisplayedText] = useState("");
  const [snapshotOpen, setSnapshotOpen] = useState(false);
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null);

  const latestQuery = useQuery({
    queryKey: ["ai-brief", "latest"],
    queryFn: () => fetchJson<ApiResponse<MarketBrief>>("/api/v1/ai/market-brief/latest"),
    retry: false,
    staleTime: 5 * 60 * 1000
  });

  const historyQuery = useQuery({
    queryKey: ["ai-brief", "history"],
    queryFn: () => fetchJson<ApiResponse<MarketBrief[]>>("/api/v1/ai/market-brief/history?limit=5"),
    retry: false,
    staleTime: 5 * 60 * 1000
  });

  const generateMutation = useMutation({
    mutationFn: () => fetchJson<ApiResponse<MarketBrief>>("/api/v1/ai/market-brief", { method: "POST" }),
    onSuccess: (response) => {
      setActiveBrief(response.data);
      setSnapshotOpen(true);
      queryClient.invalidateQueries({ queryKey: ["ai-brief"] });
    }
  });

  useEffect(() => {
    if (!activeBrief && latestQuery.data?.data) {
      setActiveBrief(latestQuery.data.data);
    }
  }, [activeBrief, latestQuery.data]);

  useEffect(() => {
    if (!activeBrief) {
      setDisplayedText("");
      return;
    }
    setDisplayedText("");
    let index = 0;
    const timer = window.setInterval(() => {
      index += 3;
      setDisplayedText(activeBrief.brief_text.slice(0, index));
      if (index >= activeBrief.brief_text.length) {
        window.clearInterval(timer);
      }
    }, 18);
    return () => window.clearInterval(timer);
  }, [activeBrief]);

  const disabled = isDisabledError(latestQuery.error) || isDisabledError(historyQuery.error) || isDisabledError(generateMutation.error);
  const loading = latestQuery.isLoading || generateMutation.isPending;
  const history = historyQuery.data?.data ?? [];
  const generatedAt = activeBrief?.generated_at ?? activeBrief?.created_at;
  const meta = useMemo(() => {
    if (!activeBrief) return "尚無摘要";
    return `${activeBrief.model} · ${activeBrief.tokens_used ?? "-"} tokens`;
  }, [activeBrief]);

  return (
    <main className="ai-brief-shell">
      <header className="ai-brief-header">
        <div>
          <p className="panel-kicker">Phase T4</p>
          <h1>AI 盤面摘要</h1>
          <span>以市場資料產生盤面描述、技術面觀察與板塊輪動摘要。</span>
        </div>
        <div className="ai-brief-actions">
          <div className="analysis-status compact">
            <Clock3 size={16} />
            {generatedAt ? `最後更新：${formatDateTime(generatedAt)}` : "尚未生成"}
          </div>
          <button
            className="primary-action"
            disabled={disabled || generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
            type="button"
          >
            {generateMutation.isPending ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            產生摘要
          </button>
        </div>
      </header>

      {disabled ? (
        <section className="ai-disabled-card">
          <Bot size={28} />
          <div>
            <h2>功能未啟用</h2>
            <p>請設定 `AI_BRIEF_ENABLED=true` 並提供 `OPENAI_API_KEY` 後再產生摘要。</p>
          </div>
        </section>
      ) : null}

      <section className="ai-brief-card">
        <div className="ai-brief-card-header">
          <div>
            <h2>摘要內容</h2>
            <span>{meta}</span>
          </div>
        </div>

        {loading ? (
          <TypingSkeleton />
        ) : generateMutation.isError && !disabled ? (
          <div className="analysis-error">{errorMessage(generateMutation.error)}</div>
        ) : activeBrief ? (
          <>
            <article className="brief-text">{displayedText}</article>
            <button className="snapshot-toggle" onClick={() => setSnapshotOpen((value) => !value)} type="button">
              {snapshotOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              資料來源快照
            </button>
            {snapshotOpen ? <SnapshotPanel snapshot={activeBrief.data_snapshot} /> : null}
          </>
        ) : latestQuery.isError ? (
          <div className="backtest-empty">尚無摘要。請按「產生摘要」建立第一份 AI 盤面摘要。</div>
        ) : (
          <div className="backtest-empty">尚無摘要。請按「產生摘要」建立第一份 AI 盤面摘要。</div>
        )}
      </section>

      <section className="ai-brief-card">
        <div className="ai-brief-card-header">
          <div>
            <h2>歷史摘要</h2>
            <span>最近 5 筆</span>
          </div>
        </div>

        {historyQuery.isLoading ? (
          <HistorySkeleton />
        ) : history.length > 0 ? (
          <div className="brief-history-list">
            {history.map((item) => (
              <div className="brief-history-item" key={item.id}>
                <button
                  onClick={() => {
                    setActiveBrief(item);
                    setExpandedHistoryId((current) => (current === item.id ? null : item.id));
                  }}
                  type="button"
                >
                  <span>{formatDateTime(item.created_at)}</span>
                  <strong>{item.brief_text.slice(0, 44)}...</strong>
                  {expandedHistoryId === item.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {expandedHistoryId === item.id ? <p>{item.brief_text}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="backtest-empty">尚無歷史摘要。</div>
        )}
      </section>

      <aside className="ai-disclaimer">{disclaimer}</aside>
    </main>
  );
}

function SnapshotPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  return (
    <div className="snapshot-panel">
      <div className="snapshot-grid">
        <section>
          <h3>Watchlist</h3>
          {(snapshot.watchlist ?? []).map((item) => (
            <div className="snapshot-row" key={item.symbol}>
              <span>{item.name}</span>
              <strong>{formatNumber(item.latest_close)}</strong>
              <em className={valueTone(item.five_day_change_pct ?? 0)}>{formatSignedPercent(item.five_day_change_pct)}</em>
            </div>
          ))}
        </section>
        <section>
          <h3>板塊輪動</h3>
          {(snapshot.sector_rotation?.top ?? []).map((item) => (
            <div className="snapshot-row" key={item.symbol}>
              <span>#{item.rank} {item.sector_name}</span>
              <strong>RS {formatRatio(item.rs_score)}</strong>
              <em className={valueTone(item.relative_return_pct)}>{formatSignedPercent(item.relative_return_pct)}</em>
            </div>
          ))}
        </section>
        <section>
          <h3>選股排行 Top 3</h3>
          {(snapshot.stock_ranking_top3 ?? []).map((item) => (
            <div className="snapshot-row" key={item.symbol}>
              <span>#{item.rank} {item.name}</span>
              <strong>{formatRatio(item.composite_score)}</strong>
              <em className={valueTone(item.period_return_pct)}>{formatSignedPercent(item.period_return_pct)}</em>
            </div>
          ))}
        </section>
        <section>
          <h3>VIX</h3>
          <div className="snapshot-row">
            <span>最新值</span>
            <strong>{formatNumber(snapshot.vix?.latest)}</strong>
          </div>
          <div className="snapshot-row">
            <span>5 日均值</span>
            <strong>{formatNumber(snapshot.vix?.five_day_average)}</strong>
          </div>
        </section>
      </div>
    </div>
  );
}

function TypingSkeleton() {
  return (
    <div className="typing-skeleton">
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="typing-skeleton compact">
      <span />
      <span />
      <span />
    </div>
  );
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const payload = await response.text();
    const error = new Error(payload || `${path} HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return (await response.json()) as T;
}

function isDisabledError(error: unknown) {
  return Boolean(error && typeof error === "object" && "status" in error && (error as { status?: number }).status === 503);
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "操作失敗";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatSignedPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function valueTone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}
