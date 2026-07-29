import type { SentimentSummary } from "../../app/ai/types";

type SentimentMetricsProps = {
  sentiment: SentimentSummary;
};

const PCR_AVERAGE = 0.85;

function formatNumber(value: number | null, digits = 2) {
  if (value === null || Number.isNaN(value)) return null;
  return value.toLocaleString("zh-TW", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function getVixStatus(vix: number | null) {
  if (vix === null || Number.isNaN(vix)) {
    return { label: "資料暫缺", tone: "neutral" };
  }
  if (vix < 15) return { label: "低波動", tone: "positive" };
  if (vix <= 25) return { label: "警戒", tone: "warning" };
  return { label: "高恐慌", tone: "negative" };
}

function getPcrDeviation(pcr: number | null) {
  if (pcr === null || Number.isNaN(pcr)) return null;
  return ((pcr - PCR_AVERAGE) / PCR_AVERAGE) * 100;
}

export function SentimentMetrics({ sentiment }: SentimentMetricsProps) {
  const vixStatus = getVixStatus(sentiment.vix);
  const pcrDeviation = getPcrDeviation(sentiment.putCallRatio);

  return (
    <div className="ai-sentiment-metrics">
      <article className="ai-sentiment-card">
        <div className="ai-sentiment-card-header">
          <span>VIX</span>
          <strong className={`ai-sentiment-badge ${vixStatus.tone}`}>{vixStatus.label}</strong>
        </div>
        {sentiment.vix === null || Number.isNaN(sentiment.vix) ? (
          <p className="ai-sentiment-missing">資料暫缺</p>
        ) : (
          <>
            <strong className="ai-sentiment-value">{formatNumber(sentiment.vix)}</strong>
            <p>市場波動狀態依 15 / 25 作為低波動、警戒與高恐慌分界。</p>
          </>
        )}
      </article>

      <article className="ai-sentiment-card">
        <div className="ai-sentiment-card-header">
          <span>Put-Call Ratio</span>
          <strong className="ai-sentiment-badge neutral">均值 {PCR_AVERAGE.toFixed(2)}</strong>
        </div>
        {sentiment.putCallRatio === null || Number.isNaN(sentiment.putCallRatio) || pcrDeviation === null ? (
          <p className="ai-sentiment-missing">資料暫缺</p>
        ) : (
          <>
            <strong className="ai-sentiment-value">{formatNumber(sentiment.putCallRatio)}</strong>
            <p className={pcrDeviation >= 0 ? "negative" : "positive"}>
              較歷史均值 {pcrDeviation >= 0 ? "+" : ""}
              {pcrDeviation.toFixed(1)}%
            </p>
          </>
        )}
      </article>
    </div>
  );
}
