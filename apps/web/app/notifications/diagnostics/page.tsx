"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ClipboardList, RefreshCw, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";

type SummaryItem = {
  job_name: string | null;
  status: string;
  reason: string | null;
  message: string;
  updated_at: string | null;
};

type RuntimeEvent = {
  id: number;
  created_at: string;
  job_name: string | null;
  notification_type: string;
  category?: "summary" | "alert" | "system";
  source?: "manual" | "background";
  status: string;
  skip_reason: string | null;
  symbol: string | null;
  topic: string | null;
  message_preview: string | null;
  chat_id_masked: string | null;
};

type JobRun = {
  id: number;
  job_name: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  targets_scanned: number;
  disabled_skipped_count: number;
  frequency_skipped_count: number;
  triggered_count: number;
  dedup_skipped_count: number;
  sent_count: number;
  error_count: number;
  final_status: string;
};

type MetricCountRow = {
  notification_type?: string;
  rule_key?: string;
  count: number;
  sent: number;
  skipped: number;
  dedup_skipped: number;
  error: number;
  no_trigger?: number;
};

type NotificationMetrics = {
  days: number;
  totals: {
    events: number;
    sent: number;
    skipped: number;
    dedup_skipped: number;
    error: number;
    manual_test: number;
    auto_trigger: number;
  };
  top_notification_types: MetricCountRow[];
  top_rule_keys: MetricCountRow[];
  manual_vs_auto: {
    manual_test: number;
    auto: number;
  };
  success_rate: number;
  noise_rate: number;
  health_hints: string[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

const summaryCards: Array<{ key: keyof DiagnosticsSummary; title: string; icon: "shield" | "send" | "list" | "alert" }> = [
  { key: "latest_market_job", title: "市場通知", icon: "shield" },
  { key: "latest_price_job", title: "價格警示", icon: "send" },
  { key: "latest_technical_job", title: "技術警示", icon: "list" },
  { key: "latest_ai_summary_job", title: "AI 摘要", icon: "alert" }
];

type DiagnosticsSummary = {
  latest_market_job: SummaryItem;
  latest_price_job: SummaryItem;
  latest_technical_job: SummaryItem;
  latest_ai_summary_job: SummaryItem;
};

const reasonLabels: Record<string, string> = {
  alerts_disabled: "總開關關閉",
  category_disabled: "分類開關關閉",
  alerts_or_category_disabled: "總開關或分類開關關閉",
  frequency_not_allowed: "摘要頻率不允許",
  dedup: "Redis 去重跳過",
  no_trigger: "未達觸發條件",
  no_chat_id: "尚未綁定 Chat ID",
  data_missing: "資料暫缺",
  error: "執行錯誤"
};

const statusLabels: Record<string, string> = {
  sent: "已送出",
  dry_run: "Dry-run",
  skipped: "已跳過",
  dedup_skipped: "去重跳過",
  error: "錯誤",
  failed: "失敗",
  empty: "尚無紀錄"
};

export default function NotificationDiagnosticsPage() {
  const summaryQuery = useQuery({
    queryKey: ["notification-diagnostics-summary"],
    queryFn: () => fetchJson<DiagnosticsSummary>("/api/v1/notifications/diagnostics/summary"),
    refetchInterval: 60_000
  });
  const eventsQuery = useQuery({
    queryKey: ["notification-events"],
    queryFn: () => fetchJson<RuntimeEvent[]>("/api/v1/notifications/events?limit=50"),
    refetchInterval: 60_000
  });
  const runsQuery = useQuery({
    queryKey: ["notification-job-runs"],
    queryFn: () => fetchJson<JobRun[]>("/api/v1/notifications/job-runs?limit=20"),
    refetchInterval: 60_000
  });
  const metricsQuery = useQuery({
    queryKey: ["notification-metrics", 7],
    queryFn: () => fetchJson<NotificationMetrics>("/api/v1/notifications/metrics?days=7"),
    refetchInterval: 60_000
  });

  const isLoading = summaryQuery.isLoading || eventsQuery.isLoading || runsQuery.isLoading || metricsQuery.isLoading;
  const isError = summaryQuery.isError || eventsQuery.isError || runsQuery.isError || metricsQuery.isError;

  function refreshAll() {
    summaryQuery.refetch();
    eventsQuery.refetch();
    runsQuery.refetch();
    metricsQuery.refetch();
  }

  return (
    <main className="notifications-shell diagnostics-shell">
      <section className="notifications-hero diagnostics-hero">
        <span>OBSERVABILITY</span>
        <div className="diagnostics-hero-row">
          <div>
            <h1>通知診斷</h1>
            <p>查看 Telegram 背景推播是否送出、為什麼跳過，以及最近 worker job 的執行狀態。</p>
          </div>
          <div className="diagnostics-actions">
            <Link className="notification-secondary-button" href="/notifications">
              <ArrowLeft size={16} />
              回通知設定
            </Link>
            <button className="notification-primary-button" onClick={refreshAll} type="button">
              <RefreshCw size={16} />
              重新整理
            </button>
          </div>
        </div>
      </section>

      {isError ? (
        <section className="notification-card notification-error-card">
          <AlertTriangle size={22} />
          <div>
            <h2>診斷資料暫時無法載入</h2>
            <p>請確認 API、PostgreSQL 與 worker 是否正常運作。</p>
          </div>
        </section>
      ) : null}

      <section className="diagnostics-summary-grid">
        {summaryCards.map((card) => {
          const item = summaryQuery.data?.[card.key];
          return (
            <article className="notification-card diagnostics-summary-card" key={card.key}>
              <div className="notification-card-header">
                <div>
                  <span>{item?.job_name ?? "尚無 job"}</span>
                  <h2>{card.title}</h2>
                </div>
                <SummaryIcon type={card.icon} />
              </div>
              {isLoading && !item ? (
                <div className="notification-skeleton compact" />
              ) : (
                <>
                  <StatusBadge status={item?.status ?? "empty"} />
                  <p>{item?.message ?? "尚無執行紀錄。"}</p>
                  <small>{item?.updated_at ? `更新：${formatDateTime(item.updated_at)}` : "尚無時間"}</small>
                </>
              )}
            </article>
          );
        })}
      </section>

      <section className="notification-card notification-card wide diagnostics-metrics-panel">
        <div className="notification-card-header">
          <div>
            <span>QUALITY METRICS</span>
            <h2>近 7 天通知品質</h2>
          </div>
          <StatusBadge status={qualityStatus(metricsQuery.data)} />
        </div>
        {metricsQuery.isLoading ? (
          <div className="notification-skeleton compact" />
        ) : (
          <>
            <div className="diagnostics-metric-grid">
              <MetricTile label="送出" value={metricsQuery.data?.totals.sent ?? 0} tone="success" />
              <MetricTile label="跳過" value={metricsQuery.data?.totals.skipped ?? 0} tone="muted" />
              <MetricTile label="去重" value={metricsQuery.data?.totals.dedup_skipped ?? 0} tone="warning" />
              <MetricTile label="錯誤" value={metricsQuery.data?.totals.error ?? 0} tone="danger" />
              <MetricTile label="手動測試" value={metricsQuery.data?.manual_vs_auto.manual_test ?? 0} tone="info" />
              <MetricTile label="背景事件" value={metricsQuery.data?.manual_vs_auto.auto ?? 0} tone="info" />
            </div>
            <div className="diagnostics-rate-row">
              <span>成功率：{formatRate(metricsQuery.data?.success_rate)}</span>
              <span>噪音率：{formatRate(metricsQuery.data?.noise_rate)}</span>
              <span>總事件：{metricsQuery.data?.totals.events ?? 0}</span>
            </div>
            <div className="diagnostics-metrics-columns">
              <TopMetricList title="最常出現的通知類型" rows={metricsQuery.data?.top_notification_types ?? []} kind="type" />
              <TopMetricList title="最常出現的規則" rows={metricsQuery.data?.top_rule_keys ?? []} kind="rule" />
            </div>
            <div className="diagnostics-health-hints">
              {(metricsQuery.data?.health_hints ?? ["尚無品質提示。"]).map((hint) => (
                <p key={hint}>{hint}</p>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="notification-card diagnostics-table-card">
        <div className="notification-card-header">
          <div>
            <span>EVENTS</span>
            <h2>最近通知事件</h2>
          </div>
        </div>
        <div className="diagnostics-table-wrap">
          <table className="diagnostics-table">
            <thead>
              <tr>
                <th>時間</th>
                <th>Job</th>
                <th>分類</th>
                <th>來源</th>
                <th>類型</th>
                <th>狀態</th>
                <th>原因</th>
                <th>標的 / 主題</th>
                <th>Chat</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {(eventsQuery.data ?? []).map((event) => (
                <tr key={event.id}>
                  <td>{formatDateTime(event.created_at)}</td>
                  <td>{event.job_name ?? "—"}</td>
                  <td><EventBadge value={event.category ?? "alert"} /></td>
                  <td><EventBadge value={event.source ?? "background"} /></td>
                  <td>{event.notification_type}</td>
                  <td><StatusBadge status={event.status} compact /></td>
                  <td>{event.skip_reason ? reasonLabels[event.skip_reason] ?? event.skip_reason : "—"}</td>
                  <td>{event.symbol ?? event.topic ?? "—"}</td>
                  <td>{event.chat_id_masked ?? "—"}</td>
                  <td className="diagnostics-preview">{event.message_preview ?? "—"}</td>
                </tr>
              ))}
              {!isLoading && !eventsQuery.data?.length ? (
                <tr>
                  <td colSpan={10}>尚無通知事件。</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="notification-card diagnostics-table-card">
        <div className="notification-card-header">
          <div>
            <span>JOB RUNS</span>
            <h2>最近 Job 執行</h2>
          </div>
        </div>
        <div className="diagnostics-table-wrap">
          <table className="diagnostics-table">
            <thead>
              <tr>
                <th>完成時間</th>
                <th>Job</th>
                <th>狀態</th>
                <th>掃描對象</th>
                <th>命中</th>
                <th>送出</th>
                <th>設定跳過</th>
                <th>頻率跳過</th>
                <th>去重</th>
                <th>錯誤</th>
                <th>耗時</th>
              </tr>
            </thead>
            <tbody>
              {(runsQuery.data ?? []).map((run) => (
                <tr key={run.id}>
                  <td>{formatDateTime(run.finished_at)}</td>
                  <td>{run.job_name}</td>
                  <td><StatusBadge status={run.final_status} compact /></td>
                  <td>{run.targets_scanned}</td>
                  <td>{run.triggered_count}</td>
                  <td>{run.sent_count}</td>
                  <td>{run.disabled_skipped_count}</td>
                  <td>{run.frequency_skipped_count}</td>
                  <td>{run.dedup_skipped_count}</td>
                  <td>{run.error_count}</td>
                  <td>{run.duration_ms} ms</td>
                </tr>
              ))}
              {!isLoading && !runsQuery.data?.length ? (
                <tr>
                  <td colSpan={11}>尚無 job 執行紀錄。</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="notification-card diagnostics-reasons">
        <div className="notification-card-header">
          <div>
            <span>WHY NOT SENT</span>
            <h2>常見跳過原因</h2>
          </div>
        </div>
        <div className="diagnostics-reason-grid">
          {Object.entries(reasonLabels).map(([key, label]) => (
            <div key={key}>
              <code>{key}</code>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function MetricTile({ label, value, tone }: { label: string; value: number; tone: "success" | "warning" | "danger" | "info" | "muted" }) {
  return (
    <div className={`diagnostics-metric-tile ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TopMetricList({ title, rows, kind }: { title: string; rows: MetricCountRow[]; kind: "type" | "rule" }) {
  return (
    <div className="diagnostics-top-list">
      <h3>{title}</h3>
      {rows.length ? rows.map((row) => {
        const label = kind === "rule" ? row.rule_key : row.notification_type;
        return (
          <div key={label ?? "unknown"}>
            <span>{label ?? "unknown"}</span>
            <strong>{row.count}</strong>
            <small>送出 {row.sent}｜跳過 {row.skipped}｜去重 {row.dedup_skipped}</small>
          </div>
        );
      }) : <p>近 7 天尚無資料。</p>}
    </div>
  );
}

function SummaryIcon({ type }: { type: "shield" | "send" | "list" | "alert" }) {
  if (type === "shield") return <ShieldCheck size={20} />;
  if (type === "send") return <Send size={20} />;
  if (type === "list") return <ClipboardList size={20} />;
  return <AlertTriangle size={20} />;
}

function StatusBadge({ status, compact }: { status: string; compact?: boolean }) {
  return (
    <span className={`diagnostics-status ${status} ${compact ? "compact" : ""}`}>
      {statusLabels[status] ?? status}
    </span>
  );
}

function EventBadge({ value }: { value: string }) {
  const labels: Record<string, string> = {
    summary: "摘要",
    alert: "警示",
    system: "系統",
    manual: "手動",
    background: "背景",
  };
  return <span className={`diagnostics-event-badge ${value}`}>{labels[value] ?? value}</span>;
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

function formatRate(value?: number) {
  if (value === undefined || Number.isNaN(value)) return "0%";
  return `${Math.round(value * 100)}%`;
}

function qualityStatus(metrics?: NotificationMetrics) {
  if (!metrics || metrics.totals.events === 0) return "empty";
  if (metrics.totals.error > 0) return "error";
  if (metrics.noise_rate >= 0.7) return "dedup_skipped";
  return "sent";
}
