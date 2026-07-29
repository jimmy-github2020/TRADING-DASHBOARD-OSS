import type { NewsItem } from "../../app/ai/types";

type NewsListProps = {
  items: NewsItem[];
};

const sentimentLabel: Record<NewsItem["sentiment"], string> = {
  positive: "正面",
  neutral: "中性",
  negative: "負面",
};

function formatScore(score: number | null) {
  if (score === null || Number.isNaN(score)) return "—";
  const sign = score > 0 ? "+" : "";
  return `${sign}${score.toFixed(2)}`;
}

export function NewsList({ items }: NewsListProps) {
  if (items.length === 0) {
    return (
      <section className="ai-news-list" aria-label="今日重要新聞">
        <div className="ai-news-list-empty">目前沒有新聞資料。</div>
      </section>
    );
  }

  return (
    <section className="ai-news-list" aria-label="今日重要新聞">
      <div className="ai-news-list-header">
        <span>今日重要新聞</span>
        <strong>{items.length} items</strong>
      </div>
      {items.map((item) => (
        <article className="ai-news-row" key={item.id}>
          <div>
            <strong>{item.title}</strong>
            <small>
              {item.source} · {item.publishedAt ?? "—"}
            </small>
          </div>
          <div className="ai-news-score-block">
            <span className={`ai-news-sentiment ${item.sentiment}`}>{sentimentLabel[item.sentiment]}</span>
            <strong>{formatScore(item.sentimentScore)}</strong>
          </div>
        </article>
      ))}
    </section>
  );
}
