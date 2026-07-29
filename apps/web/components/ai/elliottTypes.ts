export type ElliottTrend = "bullish" | "bearish" | "neutral";

export type ElliottWaveBase = {
  id: "C1" | "C2" | "C3";
  date: string;
  price: number;
  label: string;
};

export type ElliottWaveData = {
  base_id: "C1" | "C2" | "C3";
  base_date: string;
  base_price: number;
  base_reason: string;
  wave_number: string;
  wave_phase: string;
  wave_label: string;
  support: number;
  resistance: number;
  trend: ElliottTrend;
  note: string;
  all_bases: ElliottWaveBase[];
  source: "gemini" | "fallback" | string;
  generated_at: string;
};
