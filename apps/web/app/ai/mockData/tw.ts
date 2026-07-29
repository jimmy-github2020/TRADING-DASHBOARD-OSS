import type { AiMarketPageData } from "../types";

export const twMarketData: AiMarketPageData = {
  marketScope: "tw",
  marketSummary: {
    title: "台股大盤",
    primaryIndex: "^TWII",
    direction: "sideways",
    directionLabel: "震盪偏多",
    changePct: 0.46,
    turnoverLabel: "量能溫和放大",
    summary:
      "台股由電子權值與金融族群輪動支撐，短線仍以月線附近的量價結構為核心觀察。若成交量續增且站穩前高，盤勢偏向震盪墊高。",
  },
  technicalSummary: {
    symbol: "^TWII",
    trendLabel: "多方整理",
    rsi: 58.4,
    macdStatus: "柱狀體收斂，動能中性偏強",
    kdStatus: "K 值高於 D 值，仍需觀察鈍化",
    support: 45200,
    resistance: 46600,
  },
  sentimentSummary: {
    fearGreed: 63,
    vix: 19.7,
    putCallRatio: 0.92,
    label: "風險胃納中性偏樂觀",
  },
  news: [
    {
      id: "tw-news-1",
      source: "示範資料",
      title: "AI 伺服器供應鏈維持高檔出貨，法人關注電子權值股續航力",
      sentiment: "positive",
      sentimentScore: 0.62,
      publishedAt: "09:10",
    },
    {
      id: "tw-news-2",
      source: "示範資料",
      title: "匯率波動牽動出口族群評價，短線資金偏向大型權值股",
      sentiment: "neutral",
      sentimentScore: 0.08,
      publishedAt: "10:25",
    },
  ],
  rankings: [
    { symbol: "2330.TW", name: "台積電", score: 86, reason: "趨勢與基本面評分維持高檔" },
    { symbol: "2308.TW", name: "台達電", score: 81, reason: "動能回升，營收能見度佳" },
    { symbol: "0050.TW", name: "元大台灣50", score: 76, reason: "大盤代表性高，波動相對可控" },
  ],
  aiBriefs: [
    {
      provider: "all",
      status: "ready",
      title: "All AI 共識摘要",
      content: "目前 mock 共識偏向震盪偏多，正式 AI 串接將在 T5-4 補上。",
      confidence: 67,
    },
    { provider: "chatgpt", status: "empty", title: "ChatGPT", content: null, confidence: null },
    { provider: "perplexity", status: "empty", title: "Perplexity", content: null, confidence: null },
    { provider: "gemini", status: "reserved", title: "Gemini", content: null, confidence: null },
    { provider: "claude", status: "reserved", title: "Claude", content: null, confidence: null },
  ],
  socialSentiment: {
    tw: {
      platform: "threads",
      keywords: ["台積電", "台股創高", "AI 伺服器", "ETF"],
      bullishPct: 46,
      neutralPct: 38,
      bearishPct: 16,
      updatedAt: "2026-06-29T09:20:00+08:00",
    },
    us: {
      platform: "x",
      keywords: ["TSM", "NVDA", "semiconductors", "AI trade"],
      bullishPct: 52,
      neutralPct: 31,
      bearishPct: 17,
      updatedAt: "2026-06-29T01:20:00Z",
    },
  },
};
