"use client";

import { useEffect, useState } from "react";
import { FearGreedGauge } from "../../../components/ai/FearGreedGauge";
import { NewsList } from "../../../components/ai/NewsList";
import { SentimentMetrics } from "../../../components/ai/SentimentMetrics";
import { SocialSentiment } from "../../../components/ai/SocialSentiment";
import type { AiMarketPageData, MarketScope, NewsItem, SentimentSummary } from "../types";

type SentimentApiResponse = {
  vix: number | null;
  put_call_ratio: number | null;
  fear_greed_score: number | null;
  fear_greed_label: string | null;
};

type NewsApiItem = {
  title: string;
  source: string;
  url: string;
  published_at: string | null;
  sentiment: NewsItem["sentiment"];
  sentiment_score: number;
};

type NewsApiResponse = {
  items: NewsApiItem[];
  error_message: string | null;
};

type LoadState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

function mapSentimentResponse(payload: SentimentApiResponse): SentimentSummary {
  return {
    fearGreed: payload.fear_greed_score,
    vix: payload.vix,
    putCallRatio: payload.put_call_ratio,
    label: payload.fear_greed_label ?? "資料暫缺",
  };
}

function mapNewsResponse(payload: NewsApiResponse): NewsItem[] {
  return payload.items.map((item, index) => ({
    id: item.url || `${item.source}-${item.title}-${index}`,
    source: item.source,
    title: item.title,
    sentiment: item.sentiment,
    sentimentScore: item.sentiment_score,
    publishedAt: item.published_at,
  }));
}

function Screen3Skeleton({ label }: { label: string }) {
  return (
    <div className="ai-screen3-skeleton" aria-label={`${label} loading`}>
      <span>{label}</span>
      <div />
      <div />
      <div />
    </div>
  );
}

function Screen3Error() {
  return <div className="ai-screen3-error">資料載入失敗，請稍後再試</div>;
}

export function Screen3({ data, marketScope }: { data: AiMarketPageData; marketScope: MarketScope }) {
  const [sentimentState, setSentimentState] = useState<LoadState<SentimentSummary>>({
    data: null,
    error: null,
    loading: true,
  });
  const [newsState, setNewsState] = useState<LoadState<NewsItem[]>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    const controller = new AbortController();

    async function loadSentiment() {
      setSentimentState({ data: null, error: null, loading: true });
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/sentiment?scope=${marketScope}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as SentimentApiResponse;
        setSentimentState({ data: mapSentimentResponse(payload), error: null, loading: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        setSentimentState({
          data: null,
          error: error instanceof Error ? error.message : "sentiment fetch failed",
          loading: false,
        });
      }
    }

    async function loadNews() {
      setNewsState({ data: null, error: null, loading: true });
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/news?scope=${marketScope}&limit=10`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as NewsApiResponse;
        if (payload.error_message) throw new Error(payload.error_message);
        setNewsState({ data: mapNewsResponse(payload), error: null, loading: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        setNewsState({
          data: data.news,
          error: null,
          loading: false,
        });
      }
    }

    void loadSentiment();
    void loadNews();

    return () => controller.abort();
  }, [data.news, marketScope]);

  return (
    <div className="ai-screen-card ai-screen-card-wide">
      <span className="ai-screen-eyebrow">Screen 03</span>
      <h1>第三屏：情緒 & 新聞</h1>

      {sentimentState.loading ? (
        <Screen3Skeleton label="Sentiment" />
      ) : sentimentState.error || !sentimentState.data ? (
        <Screen3Error />
      ) : (
        <>
          <FearGreedGauge value={sentimentState.data.fearGreed} label={sentimentState.data.label} />
          <SentimentMetrics sentiment={sentimentState.data} />
        </>
      )}

      {newsState.loading ? (
        <Screen3Skeleton label="News" />
      ) : newsState.error || !newsState.data ? (
        <Screen3Error />
      ) : (
        <NewsList items={newsState.data} />
      )}

      <SocialSentiment tw={data.socialSentiment.tw} us={data.socialSentiment.us} />
    </div>
  );
}
