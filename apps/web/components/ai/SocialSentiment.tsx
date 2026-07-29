import type { SocialSentimentData } from "../../app/ai/types";

type SocialSentimentProps = {
  tw?: SocialSentimentData | null;
  us?: SocialSentimentData | null;
};

const platformMeta: Record<SocialSentimentData["platform"], { icon: string; title: string; source: string }> = {
  x: { icon: "X", title: "X 國外", source: "社群情緒 mock" },
  threads: { icon: "@", title: "Threads 國內", source: "社群情緒 mock" },
};

function formatUpdatedAt(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Taipei",
    hour12: false,
  });
}

function SentimentDistribution({ data }: { data: SocialSentimentData }) {
  const total = Math.max(data.bullishPct + data.neutralPct + data.bearishPct, 1);
  const bullish = (data.bullishPct / total) * 100;
  const neutral = (data.neutralPct / total) * 100;
  const bearish = (data.bearishPct / total) * 100;

  return (
    <>
      <div className="ai-social-bar" aria-label="社群情緒分布">
        <span className="bullish" style={{ width: `${bullish}%` }} />
        <span className="neutral" style={{ width: `${neutral}%` }} />
        <span className="bearish" style={{ width: `${bearish}%` }} />
      </div>
      <div className="ai-social-legend">
        <span className="bullish">多 {data.bullishPct}%</span>
        <span>中性 {data.neutralPct}%</span>
        <span className="bearish">空 {data.bearishPct}%</span>
      </div>
    </>
  );
}

function SocialCard({ data, fallbackPlatform }: { data?: SocialSentimentData | null; fallbackPlatform: "x" | "threads" }) {
  const meta = platformMeta[data?.platform ?? fallbackPlatform];

  if (!data) {
    return (
      <article className="ai-social-card empty">
        <div className="ai-social-card-header">
          <span className="ai-social-icon">{meta.icon}</span>
          <strong>{meta.title}</strong>
        </div>
        <p>資料準備中</p>
      </article>
    );
  }

  return (
    <article className="ai-social-card">
      <div className="ai-social-card-header">
        <span className="ai-social-icon">{meta.icon}</span>
        <div>
          <strong>{meta.title}</strong>
          <small>{meta.source} · {formatUpdatedAt(data.updatedAt)}</small>
        </div>
      </div>
      <div className="ai-social-keywords">
        {data.keywords.slice(0, 5).map((keyword) => (
          <span key={keyword}>{keyword}</span>
        ))}
      </div>
      <SentimentDistribution data={data} />
    </article>
  );
}

export function SocialSentiment({ tw, us }: SocialSentimentProps) {
  return (
    <section className="ai-social-sentiment" aria-label="社群情緒">
      <div className="ai-social-section-header">
        <span>社群情緒</span>
        <strong>Mock source</strong>
      </div>
      <div className="ai-social-grid">
        <SocialCard data={us} fallbackPlatform="x" />
        <SocialCard data={tw} fallbackPlatform="threads" />
      </div>
    </section>
  );
}
