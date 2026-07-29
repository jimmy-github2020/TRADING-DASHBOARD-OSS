import type { AiMarketPageData } from "../types";

export const usMarketData: AiMarketPageData = {
  marketScope: "us",
  marketSummary: {
    title: "美股大盤",
    primaryIndex: "^GSPC",
    direction: "sideways",
    directionLabel: "高檔震盪",
    changePct: -0.12,
    turnoverLabel: "科技權值量能分歧",
    summary:
      "美股大型科技股仍是盤面重心，但半導體與軟體族群動能分化。若長債殖利率續升，估值較高的成長股可能面臨短線壓力。",
  },
  technicalSummary: {
    symbol: "^GSPC",
    trendLabel: "多頭趨勢內整理",
    rsi: 55.2,
    macdStatus: "DIF 仍高於 DEA，但柱狀體降溫",
    kdStatus: "中性區間交錯",
    support: 7250,
    resistance: 7420,
  },
  sentimentSummary: {
    fearGreed: 59,
    vix: 18.9,
    putCallRatio: 0.98,
    label: "中性，避險需求略升",
  },
  news: [
    {
      id: "us-news-1",
      source: "Synthetic demo",
      title: "Mega-cap technology stocks pause as investors watch yields and earnings guidance",
      sentiment: "neutral",
      sentimentScore: -0.06,
      publishedAt: "08:40",
    },
    {
      id: "us-news-2",
      source: "Synthetic demo",
      title: "Chip demand outlook remains firm, but valuation debate intensifies",
      sentiment: "positive",
      sentimentScore: 0.48,
      publishedAt: "09:35",
    },
  ],
  rankings: [
    { symbol: "NVDA", name: "輝達", score: 84, reason: "AI 題材強，但波動偏高" },
    { symbol: "AVGO", name: "博通", score: 79, reason: "趨勢穩定且基本面延續" },
    { symbol: "TSM", name: "台積電 ADR", score: 77, reason: "半導體景氣受惠標的" },
  ],
  aiBriefs: [
    {
      provider: "all",
      status: "ready",
      title: "All AI 共識摘要",
      content: "目前 mock 共識偏向高檔震盪，正式 AI 串接將在 T5-4 補上。",
      confidence: 61,
    },
    { provider: "chatgpt", status: "empty", title: "ChatGPT", content: null, confidence: null },
    { provider: "perplexity", status: "empty", title: "Perplexity", content: null, confidence: null },
    { provider: "gemini", status: "reserved", title: "Gemini", content: null, confidence: null },
    { provider: "claude", status: "reserved", title: "Claude", content: null, confidence: null },
  ],
  socialSentiment: {
    tw: {
      platform: "threads",
      keywords: ["美股連動", "半導體", "台股夜盤"],
      bullishPct: 35,
      neutralPct: 44,
      bearishPct: 21,
      updatedAt: "2026-06-29T09:10:00+08:00",
    },
    us: {
      platform: "x",
      keywords: ["AI stocks", "rates", "earnings", "Nasdaq"],
      bullishPct: 41,
      neutralPct: 36,
      bearishPct: 23,
      updatedAt: "2026-06-29T01:10:00Z",
    },
  },
};
