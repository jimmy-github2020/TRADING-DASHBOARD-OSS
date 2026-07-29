export type MarketScope = "tw" | "us";

export type MarketDirection = "bullish" | "bearish" | "sideways";

export interface MarketSummary {
  title: string;
  primaryIndex: string;
  direction: MarketDirection;
  directionLabel: string;
  changePct: number | null;
  turnoverLabel: string | null;
  summary: string;
}

export interface TechnicalSummary {
  symbol: string;
  trendLabel: string;
  rsi: number | null;
  macdStatus: string | null;
  kdStatus: string | null;
  support: number | null;
  resistance: number | null;
}

export interface SentimentSummary {
  fearGreed: number | null;
  vix: number | null;
  putCallRatio: number | null;
  label: string;
}

export interface NewsItem {
  id: string;
  source: string;
  title: string;
  sentiment: "positive" | "neutral" | "negative";
  sentimentScore: number | null;
  publishedAt: string | null;
}

export interface RankingItem {
  symbol: string;
  name: string;
  score: number | null;
  reason: string;
}

export interface AiBrief {
  provider: "all" | "chatgpt" | "perplexity" | "gemini" | "claude";
  status: "ready" | "reserved" | "empty";
  title: string;
  content: string | null;
  confidence: number | null;
}

export interface SocialSentimentData {
  platform: "x" | "threads";
  keywords: string[];
  bullishPct: number;
  neutralPct: number;
  bearishPct: number;
  updatedAt: string | null;
}

export interface AiMarketPageData {
  marketScope: MarketScope;
  marketSummary: MarketSummary;
  technicalSummary: TechnicalSummary;
  sentimentSummary: SentimentSummary;
  news: NewsItem[];
  rankings: RankingItem[];
  aiBriefs: AiBrief[];
  socialSentiment: {
    tw?: SocialSentimentData | null;
    us?: SocialSentimentData | null;
  };
}
