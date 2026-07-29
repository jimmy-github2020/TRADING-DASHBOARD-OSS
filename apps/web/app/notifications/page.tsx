"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, CheckCircle2, Clock3, Loader2, Send, ShieldAlert, Siren, TestTube2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

type NotificationSettings = {
  telegram_bound: boolean;
  chat_id_masked: string | null;
  alerts_enabled: boolean;
  market_alerts_enabled: boolean;
  price_alerts_enabled: boolean;
  technical_alerts_enabled: boolean;
  ai_summary_enabled: boolean;
  summary_frequency: SummaryFrequency;
  last_notification_at: string | null;
  last_notification_status: string | null;
};

type SummaryFrequency = "off" | "daily" | "morning" | "evening";

type NotificationMode = {
  mode: "dry_run" | "live";
  dry_run: boolean;
};

type TestResponse = {
  status: string;
  dry_run: boolean;
  error?: string | null;
  message?: string;
};

type NotificationItemType = "morning_brief" | "closing_brief" | "market_alert" | "price_alert" | "technical_alert";

type NotificationItemStatus = {
  enabled: boolean;
  latest_manual_test_status: string | null;
  latest_manual_test_at: string | null;
  latest_background_status: string | null;
  latest_background_at: string | null;
  latest_display_status: string;
  latest_display_source: "manual_test" | "background" | null;
  latest_message: string;
  last_status?: string;
  last_event_at?: string | null;
  last_message?: string;
};

type NotificationItemStatusResponse = {
  mode: "dry_run" | "live";
  items: Record<NotificationItemType, NotificationItemStatus>;
};

type TestItemResponse = {
  ok: boolean;
  status: string;
  item_type: NotificationItemType;
  message: string;
  last_tested_at: string;
  data_source_status?: string;
  error?: string | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

const frequencyOptions: Array<{ value: SummaryFrequency; label: string; hint: string }> = [
  { value: "off", label: "關閉", hint: "不主動推送摘要" },
  { value: "daily", label: "每日", hint: "每日一次摘要" },
  { value: "morning", label: "早盤", hint: "開盤前重點" },
  { value: "evening", label: "晚間", hint: "收盤後整理" }
];

const notificationTypes = [
  {
    key: "market_alerts_enabled" as const,
    title: "市場風險警示",
    description: "台股大盤、VIX、Fear & Greed 等市場級警示。"
  },
  {
    key: "price_alerts_enabled" as const,
    title: "個股觸價警示",
    description: "依照您設定的高低價位觸發 Telegram 通知。"
  },
  {
    key: "technical_alerts_enabled" as const,
    title: "技術訊號警示",
    description: "RSI、MACD 等條件出現時通知，避免漏看重要變化。"
  },
  {
    key: "ai_summary_enabled" as const,
    title: "AI 摘要推播",
    description: "推送 AI 市場摘要與盤面觀察，不含投資建議。"
  }
];

const summaryTestItems: Array<{ type: NotificationItemType; title: string; description: string }> = [
  {
    type: "morning_brief",
    title: "早盤摘要",
    description: "使用目前資料手動發送一則測試早盤摘要。"
  },
  {
    type: "closing_brief",
    title: "晚間摘要",
    description: "使用目前資料手動發送一則測試晚間摘要。"
  }
];

const alertTestItems: Array<{ type: NotificationItemType; title: string; description: string }> = [
  {
    type: "market_alert",
    title: "市場風險警示",
    description: "手動驗證市場警示通知模板與 Telegram 發送。"
  },
  {
    type: "price_alert",
    title: "個股價格警示",
    description: "手動驗證價格警示通知模板與 Telegram 發送。"
  },
  {
    type: "technical_alert",
    title: "技術訊號警示",
    description: "手動驗證技術訊號通知模板與 Telegram 發送。"
  }
];

async function fetchSettings(): Promise<NotificationSettings> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/settings`, { cache: "no-store" });
  if (!response.ok) throw new Error("無法讀取通知設定");
  return response.json();
}

async function saveSettings(settings: NotificationSettings): Promise<NotificationSettings> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      alerts_enabled: settings.alerts_enabled,
      market_alerts_enabled: settings.market_alerts_enabled,
      price_alerts_enabled: settings.price_alerts_enabled,
      technical_alerts_enabled: settings.technical_alerts_enabled,
      ai_summary_enabled: settings.ai_summary_enabled,
      summary_frequency: settings.summary_frequency
    })
  });
  if (!response.ok) throw new Error("儲存通知設定失敗");
  return response.json();
}

async function fetchMode(): Promise<NotificationMode> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/mode`, { cache: "no-store" });
  if (!response.ok) throw new Error("無法讀取系統模式");
  return response.json();
}

async function saveMode(mode: "dry_run" | "live"): Promise<NotificationMode> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/mode`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, confirm: mode === "live" })
  });
  if (!response.ok) throw new Error("切換系統模式失敗");
  return response.json();
}

async function sendTest(kind: "summary" | "alert", dryRun: boolean): Promise<TestResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/${kind === "summary" ? "test-summary" : "test-alert"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: dryRun, force_send: true })
  });
  if (!response.ok) throw new Error(kind === "summary" ? "測試摘要發送失敗" : "測試警示發送失敗");
  return response.json();
}

async function fetchItemStatus(): Promise<NotificationItemStatusResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/item-status`, { cache: "no-store" });
  if (!response.ok) throw new Error("無法讀取細項通知狀態");
  return response.json();
}

async function sendTestItem(type: NotificationItemType, dryRun: boolean): Promise<TestItemResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/notifications/test-item`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, dry_run: dryRun })
  });
  if (!response.ok) throw new Error("細項測試發送失敗");
  return response.json();
}

export default function NotificationsPage() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<NotificationSettings | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [testingItem, setTestingItem] = useState<NotificationItemType | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["notification-settings"],
    queryFn: fetchSettings
  });
  const modeQuery = useQuery({
    queryKey: ["notification-mode"],
    queryFn: fetchMode
  });
  const itemStatusQuery = useQuery({
    queryKey: ["notification-item-status"],
    queryFn: fetchItemStatus,
    refetchInterval: 60000
  });

  const current = draft ?? settingsQuery.data ?? null;
  const isDirty = useMemo(() => {
    if (!draft || !settingsQuery.data) return false;
    return JSON.stringify(draft) !== JSON.stringify(settingsQuery.data);
  }, [draft, settingsQuery.data]);

  const mutation = useMutation({
    mutationFn: saveSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["notification-settings"], data);
      setDraft(null);
      setNotice("設定已更新");
      window.setTimeout(() => setNotice(null), 2500);
    },
    onError: () => {
      setNotice("儲存失敗，請稍後再試");
      window.setTimeout(() => setNotice(null), 3500);
    }
  });

  const modeMutation = useMutation({
    mutationFn: saveMode,
    onSuccess: (data) => {
      queryClient.setQueryData(["notification-mode"], data);
      setNotice(data.mode === "live" ? "已切換為 Live，命中條件時會發送 Telegram" : "已切換為 Dry-run，背景通知將只記錄不發送");
      window.setTimeout(() => setNotice(null), 3500);
    },
    onError: () => {
      setNotice("系統模式切換失敗");
      window.setTimeout(() => setNotice(null), 3500);
    }
  });

  const testSummaryMutation = useMutation({
    mutationFn: () => sendTest("summary", false),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["notification-settings"] });
      setNotice(data.status === "sent" ? "測試摘要已送出" : `測試摘要狀態：${data.status}`);
      window.setTimeout(() => setNotice(null), 3500);
    },
    onError: () => {
      setNotice("測試摘要發送失敗");
      window.setTimeout(() => setNotice(null), 3500);
    }
  });

  const testAlertMutation = useMutation({
    mutationFn: () => sendTest("alert", false),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["notification-settings"] });
      setNotice(data.status === "sent" ? "測試警示已送出" : `測試警示狀態：${data.status}`);
      window.setTimeout(() => setNotice(null), 3500);
    },
    onError: () => {
      setNotice("測試警示發送失敗");
      window.setTimeout(() => setNotice(null), 3500);
    }
  });

  const testItemMutation = useMutation({
    mutationFn: (type: NotificationItemType) => sendTestItem(type, modeQuery.data?.dry_run ?? true),
    onMutate: (type) => {
      setTestingItem(type);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["notification-item-status"] });
      queryClient.invalidateQueries({ queryKey: ["notification-settings"] });
      setNotice(data.message || `細項測試狀態：${data.status}`);
      window.setTimeout(() => setNotice(null), 3500);
    },
    onError: () => {
      setNotice("細項測試發送失敗");
      window.setTimeout(() => setNotice(null), 3500);
    },
    onSettled: () => {
      setTestingItem(null);
    }
  });

  function update<K extends keyof NotificationSettings>(key: K, value: NotificationSettings[K]) {
    if (!current) return;
    setDraft({ ...current, [key]: value });
  }

  function changeMode(next: "dry_run" | "live") {
    if (next === modeQuery.data?.mode || modeMutation.isPending) return;
    if (next === "live") {
      const confirmed = window.confirm("切換到 Live 後，背景通知在命中條件時會真正發送 Telegram。是否確認切換？");
      if (!confirmed) return;
    }
    modeMutation.mutate(next);
  }

  if (settingsQuery.isLoading) {
    return (
      <main className="notifications-shell">
        <section className="notifications-hero">
          <span>TELEGRAM</span>
          <h1>通知設定</h1>
          <p>正在載入 Telegram 警示、摘要與推播偏好。</p>
        </section>
        <div className="notifications-grid">
          <div className="notification-skeleton" />
          <div className="notification-skeleton" />
          <div className="notification-skeleton wide" />
        </div>
      </main>
    );
  }

  if (settingsQuery.isError || !current) {
    return (
      <main className="notifications-shell">
        <section className="notification-card notification-error-card">
          <ShieldAlert size={22} />
          <div>
            <h1>通知設定暫時無法載入</h1>
            <p>請確認 API 服務是否正常，稍後再重新整理。</p>
          </div>
        </section>
      </main>
    );
  }

  const disabledByBinding = !current.telegram_bound;

  return (
    <main className="notifications-shell">
      <section className="notifications-hero">
        <span>TELEGRAM</span>
        <h1>通知設定</h1>
        <p>管理 Telegram 警示、AI 摘要與推播偏好。Web 設定會與 Telegram 指令共用同一份後端設定。</p>
      </section>

      {notice ? <div className="notification-toast">{notice}</div> : null}

      <section className="notifications-grid">
        <article className="notification-card wide notification-mode-card">
          <div className="notification-card-header">
            <div>
              <span>系統模式</span>
              <h2>背景通知執行模式</h2>
            </div>
            <span className={`notification-mode-badge ${modeQuery.data?.mode === "live" ? "live" : "dry"}`}>
              {modeQuery.data?.mode === "live" ? "Live" : "Dry-run"}
            </span>
          </div>
          <div className={`notification-mode-notice ${modeQuery.data?.mode === "live" ? "live" : "dry"}`}>
            {modeQuery.data?.mode === "live"
              ? "目前為 Live，命中條件時將真正發送 Telegram。"
              : "目前為 Dry-run，背景通知只記錄不發送 Telegram。"}
          </div>
          <p>
            Dry-run 會執行判斷並寫入診斷紀錄，但不會真的發送 Telegram。Live 則會在條件命中時實際推播。
          </p>
          <div className="notification-mode-toggle" role="group" aria-label="通知系統模式">
            <button
              className={modeQuery.data?.mode !== "live" ? "active" : ""}
              disabled={modeMutation.isPending}
              onClick={() => changeMode("dry_run")}
              type="button"
            >
              Dry-run
            </button>
            <button
              className={modeQuery.data?.mode === "live" ? "active live" : ""}
              disabled={modeMutation.isPending}
              onClick={() => changeMode("live")}
              type="button"
            >
              Live
            </button>
          </div>
        </article>

        <article className="notification-card binding-card">
          <div className="notification-card-header">
            <div>
              <span>綁定狀態</span>
              <h2>Telegram Bot</h2>
            </div>
            <StatusPill active={current.telegram_bound} activeText="已綁定" inactiveText="未綁定" />
          </div>
          {current.telegram_bound ? (
            <p>
              Chat ID：<strong>{current.chat_id_masked}</strong>。您可以直接調整下方通知設定。
            </p>
          ) : (
            <p>請先在 Telegram 對 Bot 輸入 <code>/start</code> 完成綁定；偏好仍可先儲存，但目前無法實際推播。</p>
          )}
        </article>

        <article className="notification-card">
          <div className="notification-card-header">
            <div>
              <span>總開關</span>
              <h2>所有 Telegram 警示</h2>
            </div>
            {current.alerts_enabled ? <Bell size={20} /> : <BellOff size={20} />}
          </div>
          <SettingRow
            title="啟用通知"
            description="控制條件觸發警示是否送出。Telegram /alert on/off 也會同步改這個欄位。"
            checked={current.alerts_enabled}
            onChange={(checked) => update("alerts_enabled", checked)}
          />
        </article>

        <article className="notification-card notification-test-card">
          <div className="notification-card-header">
            <div>
              <span>摘要通知</span>
              <h2>固定排程摘要</h2>
            </div>
            <TestTube2 size={20} />
          </div>
          <p>摘要通知用於早盤、晚間或每日整理。測試摘要會使用當下資料並標示為手動測試。</p>
          <button
            className="notification-primary-button"
            disabled={disabledByBinding || testSummaryMutation.isPending}
            onClick={() => testSummaryMutation.mutate()}
            type="button"
          >
            {testSummaryMutation.isPending ? <Loader2 className="spin" size={16} /> : null}
            發送測試摘要
          </button>
          {disabledByBinding ? <small>請先在 Telegram 對 Bot 輸入 /start 完成綁定。</small> : null}
        </article>

        <article className="notification-card notification-test-card">
          <div className="notification-card-header">
            <div>
              <span>警示通知</span>
              <h2>條件觸發提醒</h2>
            </div>
            <Siren size={20} />
          </div>
          <p>警示通知用於價格、技術訊號與市場風險。測試警示只驗證發送鏈路，不代表市場條件已命中。</p>
          <button
            className="notification-primary-button"
            disabled={disabledByBinding || testAlertMutation.isPending}
            onClick={() => testAlertMutation.mutate()}
            type="button"
          >
            {testAlertMutation.isPending ? <Loader2 className="spin" size={16} /> : null}
            發送測試警示
          </button>
          {disabledByBinding ? <small>請先在 Telegram 對 Bot 輸入 /start 完成綁定。</small> : null}
        </article>

        <article className="notification-card wide notification-item-console">
          <div className="notification-card-header">
            <div>
              <span>細項測試</span>
              <h2>通知子項控制台</h2>
            </div>
            <span className={`notification-mode-badge ${itemStatusQuery.data?.mode === "live" ? "live" : "dry"}`}>
              {itemStatusQuery.data?.mode === "live" ? "Live" : "Dry-run"}
            </span>
          </div>
          <p>每個通知子項可單獨測試，並顯示最近一次手動測試或背景 job 狀態。測試訊息會清楚標示為 manual test。</p>
          <NotificationItemGroup
            title="摘要通知"
            description="固定排程或時段型通知，用於整理市場資訊；手動測試不代表正式排程剛剛觸發。"
            items={summaryTestItems}
            statuses={itemStatusQuery.data?.items}
            disabled={disabledByBinding}
            pendingItem={testingItem}
            onTest={(type) => testItemMutation.mutate(type)}
          />
          <NotificationItemGroup
            title="警示通知"
            description="條件命中時發送的即時提醒；手動測試只驗證模板與發送鏈路，不代表目前市場異常。"
            items={alertTestItems}
            statuses={itemStatusQuery.data?.items}
            disabled={disabledByBinding}
            pendingItem={testingItem}
            onTest={(type) => testItemMutation.mutate(type)}
          />
        </article>

        <article className="notification-card wide">
          <div className="notification-card-header">
            <div>
              <span>通知類型</span>
              <h2>警示與摘要</h2>
            </div>
            {disabledByBinding ? <span className="notification-muted">等待 /start 綁定</span> : null}
          </div>
          <div className="notification-type-list">
            {notificationTypes.map((item) => (
              <SettingRow
                key={item.key}
                title={item.title}
                description={item.description}
                checked={Boolean(current[item.key])}
                disabled={disabledByBinding}
                onChange={(checked) => update(item.key, checked)}
              />
            ))}
          </div>
        </article>

        <article className="notification-card">
          <div className="notification-card-header">
            <div>
              <span>摘要頻率</span>
              <h2>AI / 市場摘要</h2>
            </div>
            <Clock3 size={20} />
          </div>
          <div className="summary-frequency-control" role="radiogroup" aria-label="摘要通知頻率">
            {frequencyOptions.map((option) => (
              <button
                className={current.summary_frequency === option.value ? "active" : ""}
                key={option.value}
                onClick={() => update("summary_frequency", option.value)}
                type="button"
              >
                <strong>{option.label}</strong>
                <span>{option.hint}</span>
              </button>
            ))}
          </div>
        </article>

        <article className="notification-card">
          <div className="notification-card-header">
            <div>
              <span>最近狀態</span>
              <h2>推播紀錄摘要</h2>
            </div>
            <Send size={20} />
          </div>
          <div className="notification-status-summary">
            <span>最後推播</span>
            <strong>{current.last_notification_at ? formatDateTime(current.last_notification_at) : "尚無紀錄"}</strong>
            <span>狀態</span>
            <strong>{formatStatus(current.last_notification_status)}</strong>
          </div>
        </article>

        <article className="notification-card wide">
          <div className="notification-card-header">
            <div>
              <span>說明</span>
              <h2>Telegram 指令仍可使用</h2>
            </div>
            <CheckCircle2 size={20} />
          </div>
          <p className="notification-help">
            您仍可在 Telegram 使用 <code>/alert on</code>、<code>/alert off</code>、<code>/summary</code>、
            <code>/market</code>、<code>/vix</code>、<code>/watchlist</code>。Web 設定頁與 Bot 指令會讀寫同一份通知偏好。
          </p>
          <Link className="notification-secondary-button" href="/notifications/diagnostics">
            查看通知診斷
          </Link>
        </article>
      </section>

      <div className="notifications-actions">
        <button
          className="notification-secondary-button"
          disabled={!isDirty || mutation.isPending}
          onClick={() => setDraft(null)}
          type="button"
        >
          還原
        </button>
        <button
          className="notification-primary-button"
          disabled={!isDirty || mutation.isPending}
          onClick={() => mutation.mutate(current)}
          type="button"
        >
          {mutation.isPending ? <Loader2 className="spin" size={16} /> : null}
          儲存設定
        </button>
      </div>
    </main>
  );
}

function SettingRow({
  title,
  description,
  checked,
  disabled,
  onChange
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className={`notification-setting-row ${disabled ? "disabled" : ""}`}>
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      <button
        aria-pressed={checked}
        className={`notification-switch ${checked ? "on" : ""}`}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        type="button"
      >
        <span />
      </button>
    </div>
  );
}

function NotificationItemGroup({
  title,
  description,
  items,
  statuses,
  disabled,
  pendingItem,
  onTest
}: {
  title: string;
  description: string;
  items: Array<{ type: NotificationItemType; title: string; description: string }>;
  statuses?: Record<NotificationItemType, NotificationItemStatus>;
  disabled: boolean;
  pendingItem: NotificationItemType | null;
  onTest: (type: NotificationItemType) => void;
}) {
  return (
    <div className="notification-item-group">
      <h3>{title}</h3>
      <p>{description}</p>
      <div className="notification-item-list">
        {items.map((item) => (
          <NotificationItemRow
            disabled={disabled}
            item={item}
            key={item.type}
            loading={pendingItem === item.type}
            onTest={() => onTest(item.type)}
            status={statuses?.[item.type]}
          />
        ))}
      </div>
    </div>
  );
}

function NotificationItemRow({
  item,
  status,
  disabled,
  loading,
  onTest
}: {
  item: { type: NotificationItemType; title: string; description: string };
  status?: NotificationItemStatus;
  disabled: boolean;
  loading: boolean;
  onTest: () => void;
}) {
  const displayStatus = status?.latest_display_status ?? status?.last_status ?? "empty";
  const displaySource = status?.latest_display_source;
  const displayAt = status?.latest_display_source === "manual_test"
    ? status?.latest_manual_test_at
    : status?.latest_background_at ?? status?.last_event_at;
  const displayMessage = status?.latest_message ?? status?.last_message ?? "尚無測試紀錄";
  return (
    <div className="notification-item-row">
      <div className="notification-item-main">
        <div>
          <strong>{item.title}</strong>
          <span>{item.description}</span>
        </div>
        <span className={`notification-status-pill ${status?.enabled ? "active" : ""}`}>
          {status?.enabled ? "已啟用" : "未啟用"}
        </span>
      </div>
      <div className="notification-item-meta">
        <span className={`notification-item-status ${statusClass(displayStatus)}`}>{formatItemStatus(displayStatus)}</span>
        <span className={`notification-source-badge ${displaySource === "manual_test" ? "manual" : "background"}`}>
          {displaySource === "manual_test" ? "最近手動測試" : displaySource === "background" ? "最近背景結果" : "尚無來源"}
        </span>
        <span>{displayAt ? formatDateTime(displayAt) : "尚無紀錄"}</span>
        <span title={displayMessage}>{displayMessage}</span>
        <span className="notification-mini-source">test：{formatItemStatus(status?.latest_manual_test_status ?? "empty")}</span>
        <span className="notification-mini-source">background：{formatItemStatus(status?.latest_background_status ?? "empty")}</span>
      </div>
      <button className="notification-secondary-button" disabled={disabled || loading} onClick={onTest} type="button">
        {loading ? <Loader2 className="spin" size={15} /> : null}
        測試
      </button>
    </div>
  );
}

function StatusPill({
  active,
  activeText,
  inactiveText
}: {
  active: boolean;
  activeText: string;
  inactiveText: string;
}) {
  return <span className={`notification-status-pill ${active ? "active" : ""}`}>{active ? activeText : inactiveText}</span>;
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

function formatStatus(status: string | null) {
  if (!status) return "尚無";
  if (status === "sent") return "已送出";
  if (status === "failed") return "失敗";
  if (status === "dry_run") return "Dry-run";
  return status;
}

function formatItemStatus(status: string) {
  const labels: Record<string, string> = {
    empty: "尚無",
    sent: "已送出",
    dry_run: "Dry-run",
    rate_limited: "節流中",
    frequency_not_allowed: "時段不符",
    category_disabled: "分類關閉",
    alerts_disabled: "總開關關閉",
    no_chat_id: "未綁定",
    no_trigger: "未命中",
    error: "錯誤",
    failed: "失敗",
  };
  return labels[status] ?? status;
}

function statusClass(status: string) {
  if (status === "sent") return "success";
  if (status === "dry_run") return "info";
  if (["rate_limited", "frequency_not_allowed", "no_chat_id"].includes(status)) return "warning";
  if (["category_disabled", "alerts_disabled", "empty", "no_trigger"].includes(status)) return "muted";
  if (["error", "failed"].includes(status)) return "danger";
  return "muted";
}
