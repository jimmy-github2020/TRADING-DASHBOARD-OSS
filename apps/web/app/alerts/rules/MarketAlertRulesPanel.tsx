"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, Bell, BellOff, FlaskConical, Gauge, Lightbulb, Loader2, RefreshCw, Save, Split, Zap } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { InlineHelp } from "../../../components/InlineHelp";

type AlertRule = {
  id: number;
  rule_key: string;
  name: string;
  category: "market" | "macro";
  metric_source: string;
  operator: string;
  threshold_value: number | null;
  threshold_min: number | null;
  threshold_max: number | null;
  comparison_window: string;
  enabled: boolean;
  severity: "info" | "warning" | "critical";
  notify_enabled: boolean;
  description: string | null;
  updated_at: string | null;
};

type EvaluationResult = {
  evaluated_at?: string;
  rule_key: string;
  name: string;
  current_value: number | null;
  matched: boolean;
  reason: string;
  notify_candidate: boolean;
  notification_type: string;
  severity: "info" | "warning" | "critical";
  data_available?: boolean;
};

type EvaluationResponse = {
  evaluated_at: string;
  results: EvaluationResult[];
};

type RuleQuality = {
  rule_key: string;
  name: string;
  enabled: boolean;
  notify_enabled: boolean;
  trigger_count: number;
  sent_count: number;
  dedup_skipped_count: number;
  skipped_disabled_count: number;
  skipped_frequency_count: number;
  error_count: number;
  manual_test_count: number;
  no_trigger_count: number;
  delivery_rate: number;
  dedup_rate: number;
  actionability_hint: string;
};

type QualityResponse = {
  days: number;
  generated_at: string;
  rules: RuleQuality[];
};

type RecommendationItem = {
  rule_key: string;
  recommendation_status: "active" | "none";
  recommendation_type: string;
  suggested_action: string;
  suggested_value: number | null;
  reason: string;
  confidence: "low" | "medium" | "high";
};

type RecommendationResponse = {
  enabled: boolean;
  days: number;
  generated_at?: string;
  items: RecommendationItem[];
};

type RulePatch = {
  enabled?: boolean;
  notify_enabled?: boolean;
  threshold_value?: number;
  threshold_min?: number;
  threshold_max?: number;
  severity?: "info" | "warning" | "critical";
  description?: string;
};

type RulePresetName = "conservative" | "standard" | "sensitive";

type RulePreset = {
  label: string;
  description: string;
  rules: Record<string, RulePatch>;
};

const rulePresets: Record<RulePresetName, RulePreset> = {
  conservative: {
    label: "保守預設",
    description: "降低提醒頻率，適合只想收到較明顯市場變化。",
    rules: {
      twii_pct_move: { threshold_min: -2.5, threshold_max: 2.5, enabled: true },
      vix_high: { threshold_value: 22, enabled: true },
      fear_greed_extreme: { threshold_min: 15, threshold_max: 85, enabled: true },
      oil_price_pct_move: { threshold_min: -4, threshold_max: 4, enabled: false }
    }
  },
  standard: {
    label: "標準預設",
    description: "平衡提醒頻率與敏感度，適合作為日常監控基準。",
    rules: {
      twii_pct_move: { threshold_min: -2, threshold_max: 2, enabled: true },
      vix_high: { threshold_value: 20, enabled: true },
      fear_greed_extreme: { threshold_min: 20, threshold_max: 80, enabled: true },
      oil_price_pct_move: { threshold_min: -3, threshold_max: 3, enabled: false }
    }
  },
  sensitive: {
    label: "敏感預設",
    description: "較早提醒市場變化，通知頻率可能較高。",
    rules: {
      twii_pct_move: { threshold_min: -1.5, threshold_max: 1.5, enabled: true },
      vix_high: { threshold_value: 18, enabled: true },
      fear_greed_extreme: { threshold_min: 25, threshold_max: 75, enabled: true },
      oil_price_pct_move: { threshold_min: -2.5, threshold_max: 2.5, enabled: false }
    }
  }
};

const ruleGuidance: Record<string, { usage: string; standard: string }> = {
  twii_pct_move: {
    usage: "當台灣加權指數單日漲跌超過設定區間時提醒。",
    standard: "標準預設：單日變動超過 ±2% 時提醒。"
  },
  vix_high: {
    usage: "當 VIX 高於設定門檻時提醒，常用於觀察市場避險情緒升溫。",
    standard: "標準預設：VIX >= 20。"
  },
  fear_greed_extreme: {
    usage: "當指數小於等於下界（極度恐懼）或大於等於上界（極度貪婪）時提醒。",
    standard: "標準預設：Fear & Greed <= 20 或 >= 80。"
  },
  oil_price_pct_move: {
    usage: "當 Brent 單日波動超過設定區間時提醒，作為宏觀風險輔助觀察。",
    standard: "標準預設：單日變動超過 ±3%，預設停用。"
  }
};

const shortcutCards = [
  {
    key: "technical",
    title: "Strategies",
    description: "管理 RSI、MACD、KD、均線與布林等技術指標型規則。",
    href: "/strategies?tab=technical",
    icon: Activity,
    active: false,
    action: "前往技術策略"
  },
  {
    key: "market",
    title: "警示規則中心",
    description: "管理 TWII、VIX、Fear & Greed、油價等市場與宏觀風險規則。",
    href: "/strategies?tab=market#market-macro-alerts",
    icon: Gauge,
    active: true,
    action: "前往市場警示"
  },
  {
    key: "notifications",
    title: "Notifications",
    description: "管理規則命中後是否推播、Dry-run / Live 模式、測試與最近狀態。",
    href: "/notifications",
    icon: Bell,
    active: false,
    action: "前往通知設定"
  },
  {
    key: "diagnostics",
    title: "Diagnostics",
    description: "查看規則命中、未命中、資料缺失與推播結果。",
    href: "/notifications/diagnostics",
    icon: AlertTriangle,
    active: false,
    action: "前往通知診斷"
  }
];

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error ${response.status}`);
  }
  return response.json();
}

export function MarketAlertRulesPanel({
  compact = false,
  showHero = true
}: {
  compact?: boolean;
  showHero?: boolean;
}) {
  const queryClient = useQueryClient();
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [ruleTestResults, setRuleTestResults] = useState<Record<string, EvaluationResult & { evaluated_at: string }>>({});
  const rulesQuery = useQuery({
    queryKey: ["alert-rules"],
    queryFn: () => fetchJson<AlertRule[]>("/api/v1/alert-rules")
  });
  const qualityQuery = useQuery({
    queryKey: ["alert-rules-quality", 7],
    queryFn: () => fetchJson<QualityResponse>("/api/v1/alert-rules/quality?days=7")
  });
  const recommendationQuery = useQuery({
    queryKey: ["alert-rules-recommendations", 7],
    queryFn: () => fetchJson<RecommendationResponse>("/api/v1/alert-rules/recommendations?days=7")
  });

  const evaluateMutation = useMutation({
    mutationFn: () => fetchJson<EvaluationResponse>("/api/v1/alert-rules/evaluate", { method: "POST" }),
    onSuccess: (data) => setEvaluation(data)
  });

  const applyPresetMutation = useMutation({
    mutationFn: async (presetName: RulePresetName) => {
      const preset = rulePresets[presetName];
      await Promise.all(
        Object.entries(preset.rules).map(([ruleKey, payload]) =>
          fetchJson<AlertRule>(`/api/v1/alert-rules/${ruleKey}`, {
            method: "PATCH",
            body: JSON.stringify(payload)
          })
        )
      );
      return presetName;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
      queryClient.invalidateQueries({ queryKey: ["alert-rules-quality", 7] });
      setEvaluation(null);
      setRuleTestResults({});
    }
  });
  const recommendationToggleMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      fetchJson<{ enabled: boolean }>("/api/v1/alert-rules/recommendations/settings", {
        method: "PUT",
        body: JSON.stringify({ enabled })
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules-recommendations", 7] });
    }
  });

  const groupedRules = useMemo(() => {
    const rules = rulesQuery.data ?? [];
    return {
      market: rules.filter((rule) => rule.category === "market"),
      macro: rules.filter((rule) => rule.category === "macro")
    };
  }, [rulesQuery.data]);

  return (
    <section className={compact ? "alert-rules-panel embedded" : "alert-rules-shell"}>
      {showHero ? (
        <section className="alert-rules-hero">
          <span>ALERT RULE CENTER</span>
          <div className="alert-rules-hero-row">
            <div>
              <div className="alert-rules-title-with-help">
                <h1>警示規則中心</h1>
                <InlineHelp
                  label="警示規則中心說明"
                  content="管理市場與宏觀警示規則；技術策略規則仍由 Strategies 管理。規則命中後是否推播，仍由通知設定與 Dry-run / Live 模式決定。"
                />
              </div>
            </div>
            <div className="alert-rules-actions">
              <Link className="notification-secondary-button" href="/strategies?tab=technical">
                <Split size={16} />
                技術策略
              </Link>
              <Link className="notification-secondary-button" href="/notifications">
                <Bell size={16} />
                通知設定
              </Link>
              <button
                className="notification-primary-button"
                disabled={evaluateMutation.isPending}
                onClick={() => evaluateMutation.mutate()}
                type="button"
              >
                {evaluateMutation.isPending ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                立即評估
              </button>
            </div>
          </div>
        </section>
      ) : (
        <div className="alert-rules-inline-actions">
          <button
            className="notification-primary-button"
            disabled={evaluateMutation.isPending}
            onClick={() => evaluateMutation.mutate()}
            type="button"
          >
            {evaluateMutation.isPending ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            立即評估市場規則
          </button>
        </div>
      )}

      <section className="alert-rules-explain-grid">
        {shortcutCards.map((card) => {
          const Icon = card.icon;
          return (
            <Link
              aria-label={`${card.action}：${card.title}`}
              className={`notification-card alert-rules-explain-card clickable ${card.active ? "active" : ""}`}
              href={card.href}
              key={card.key}
            >
              <Icon size={18} />
              <div>
                <h2>{card.title}</h2>
                <small>{card.action}</small>
              </div>
            </Link>
          );
        })}
      </section>

      <section className="notification-card alert-rules-preset-card">
        <div className="notification-card-header">
          <div>
            <span>PRESETS</span>
            <div className="alert-rules-card-title-with-help">
              <h2>快速套用建議值</h2>
              <InlineHelp
                label="快速套用建議值說明"
                content="套用 preset 會更新四條市場 / 宏觀規則的門檻與啟用狀態；可推播開關會保留原設定。"
              />
            </div>
          </div>
        </div>
        <div className="alert-rules-preset-grid">
          {(Object.entries(rulePresets) as Array<[RulePresetName, RulePreset]>).map(([key, preset]) => (
            <button
              className="alert-rules-preset-button"
              disabled={applyPresetMutation.isPending}
              key={key}
              onClick={() => {
                if (window.confirm(`套用「${preset.label}」會更新 TWII / VIX / Fear & Greed / Oil 的門檻設定，是否繼續？`)) {
                  applyPresetMutation.mutate(key);
                }
              }}
              type="button"
            >
              {applyPresetMutation.isPending ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              <strong>{preset.label}</strong>
              <span>{preset.description}</span>
            </button>
          ))}
        </div>
        {applyPresetMutation.isError ? <p className="alert-rules-preset-error">套用預設失敗，請稍後再試。</p> : null}
      </section>

      <section className="notification-card alert-rules-quality-card">
        <div className="notification-card-header">
          <div>
            <span>QUALITY</span>
            <div className="alert-rules-card-title-with-help">
              <h2>近 7 天通知品質</h2>
              <InlineHelp
                label="近 7 天通知品質說明"
                content="用既有 runtime events 聚合每條規則的命中、送出、dedup、手動測試與 no-trigger 狀態，協助判斷門檻是否太敏感或太嚴。"
              />
            </div>
          </div>
          {qualityQuery.data?.generated_at ? <small>{formatDateTime(qualityQuery.data.generated_at)}</small> : null}
        </div>
        {qualityQuery.isLoading ? (
          <div className="notification-skeleton" />
        ) : qualityQuery.isError ? (
          <p className="alert-rules-preset-error">品質指標暫時無法載入。</p>
        ) : (
          <div className="alert-rules-quality-list">
            {(qualityQuery.data?.rules ?? []).map((quality) => (
              <article className="alert-rules-quality-row" key={quality.rule_key}>
                <div className="alert-rules-quality-title">
                  <strong>{quality.name}</strong>
                  <span>{quality.rule_key}</span>
                </div>
                <div className="alert-rules-quality-metrics">
                  <span>觸發 <strong>{quality.trigger_count}</strong></span>
                  <span>送出 <strong>{quality.sent_count}</strong></span>
                  <span>dedup <strong>{quality.dedup_skipped_count}</strong></span>
                  <span>手動 <strong>{quality.manual_test_count}</strong></span>
                  <span>未命中 <strong>{quality.no_trigger_count}</strong></span>
                </div>
                <p>{quality.actionability_hint}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="notification-card alert-rules-recommendation-card">
        <div className="notification-card-header">
          <div>
            <span>RECOMMENDATION ENGINE</span>
            <div className="alert-rules-card-title-with-help">
              <h2>規則調整建議</h2>
              <InlineHelp
                label="規則調整建議說明"
                content="依近 7 天規則品質指標產生只讀建議；不會自動修改任何 alert rule。"
              />
            </div>
          </div>
          <button
            className={`notification-switch ${recommendationQuery.data?.enabled ? "on" : ""}`}
            disabled={recommendationToggleMutation.isPending || recommendationQuery.isLoading}
            onClick={() => recommendationToggleMutation.mutate(!recommendationQuery.data?.enabled)}
            type="button"
            aria-label={recommendationQuery.data?.enabled ? "停用建議模組" : "啟用建議模組"}
          >
            <span />
          </button>
        </div>
        {recommendationQuery.isLoading ? (
          <div className="notification-skeleton" />
        ) : recommendationQuery.isError ? (
          <p className="alert-rules-preset-error">建議模組狀態暫時無法載入。</p>
        ) : !recommendationQuery.data?.enabled ? (
          <div className="alert-rules-recommendation-disabled">
            <Lightbulb size={18} />
            <div>
              <strong>規則調整建議模組目前已停用</strong>
              <span>啟用後，系統會根據近 7 天 rule quality 指標提供調整方向與原因。</span>
            </div>
          </div>
        ) : (
          <div className="alert-rules-recommendation-list">
            {recommendationQuery.data.items.length ? recommendationQuery.data.items.map((item) => (
              <article className={`alert-rules-recommendation-row ${item.recommendation_status}`} key={item.rule_key}>
                <div className="alert-rules-recommendation-title">
                  <strong>{ruleDisplayName(item.rule_key)}</strong>
                  <span>{item.rule_key}</span>
                </div>
                <span className={`alert-rules-confidence ${item.confidence}`}>{confidenceLabel(item.confidence)}</span>
                <div>
                  <span>{recommendationTypeLabel(item.recommendation_type)}</span>
                  <p>{item.reason}</p>
                  {item.suggested_value !== null ? <small>參考建議值：{item.suggested_value}</small> : null}
                </div>
              </article>
            )) : (
              <p className="alert-rules-muted">目前無明確調整建議。</p>
            )}
          </div>
        )}
      </section>

      {rulesQuery.isError ? (
        <section className="notification-card notification-error-card alert-rules-error">
          <AlertTriangle size={22} />
          <div>
            <h2>規則資料暫時無法載入</h2>
            <p>請確認 API 與 PostgreSQL 是否正常。</p>
          </div>
        </section>
      ) : null}

      <section className="alert-rules-section" id="market-macro-alerts">
        <div className="alert-rules-section-header">
          <div>
            <span>MARKET</span>
            <div className="alert-rules-section-title-with-help">
              <h2>市場規則</h2>
              <InlineHelp
                label="市場規則說明"
                content="大盤指數與市場層級變動，命中後屬於 market_alert。這類規則偏向整體市場風險，不等同於個股技術策略。"
              />
            </div>
          </div>
        </div>
        <div className="alert-rules-grid">
          {rulesQuery.isLoading ? <RuleSkeleton /> : groupedRules.market.map((rule) => <RuleCard key={rule.rule_key} rule={rule} />)}
        </div>
      </section>

      <section className="alert-rules-section">
        <div className="alert-rules-section-header">
          <div>
            <span>MACRO</span>
            <div className="alert-rules-section-title-with-help">
              <h2>宏觀規則</h2>
              <InlineHelp
                label="宏觀規則說明"
                content="波動率、情緒與商品價格，作為市場 regime 觀察訊號。資料缺失時會顯示 unavailable reason，不會讓整頁故障。"
              />
            </div>
          </div>
        </div>
        <div className="alert-rules-grid">
          {rulesQuery.isLoading ? <RuleSkeleton /> : groupedRules.macro.map((rule) => <RuleCard key={rule.rule_key} rule={rule} />)}
        </div>
      </section>

      <section className="notification-card alert-rules-evaluation-card">
        <div className="notification-card-header">
          <div>
            <span>EVALUATION</span>
            <h2>手動評估結果</h2>
          </div>
          {evaluation?.evaluated_at ? <small>{formatDateTime(evaluation.evaluated_at)}</small> : null}
        </div>
        {evaluateMutation.isError ? (
          <p className="alert-rules-muted">評估失敗，請稍後再試。</p>
        ) : evaluation ? (
          <div className="alert-rules-evaluation-list">
            {evaluation.results.map((result) => (
              <article className={`alert-rules-result ${result.matched ? "matched" : ""}`} key={result.rule_key}>
                <div>
                  <strong>{result.name}</strong>
                  <small>{result.rule_key}</small>
                </div>
                <StatusPill matched={result.matched} />
                <span>{formatNumber(result.current_value)}</span>
                <p>{result.reason}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="alert-rules-muted">按下「立即評估」後，這裡會顯示每條規則的 current value、是否命中與原因。</p>
        )}
      </section>
    </section>
  );

  function RuleCard({ rule }: { rule: AlertRule }) {
    const [draft, setDraft] = useState({
      enabled: rule.enabled,
      notify_enabled: rule.notify_enabled,
      threshold_value: rule.threshold_value?.toString() ?? "",
      threshold_min: rule.threshold_min?.toString() ?? "",
      threshold_max: rule.threshold_max?.toString() ?? "",
      severity: rule.severity,
      description: rule.description ?? ""
    });

    const patchMutation = useMutation({
      mutationFn: (payload: RulePatch) =>
        fetchJson<AlertRule>(`/api/v1/alert-rules/${rule.rule_key}`, {
          method: "PATCH",
          body: JSON.stringify(payload)
        }),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
      }
    });
    const testMutation = useMutation({
      mutationFn: () =>
        fetchJson<EvaluationResult & { evaluated_at: string; data_available: boolean }>(
          `/api/v1/alert-rules/${rule.rule_key}/evaluate`,
          { method: "POST" }
      ),
      onSuccess: (data) => {
        setRuleTestResults((current) => ({ ...current, [rule.rule_key]: data }));
        queryClient.invalidateQueries({ queryKey: ["alert-rules-quality", 7] });
      }
    });

    const thresholdLabel = rule.operator === "outside_range" ? "區間門檻" : "單值門檻";
    const latestTest = ruleTestResults[rule.rule_key];
    const guidance = ruleGuidance[rule.rule_key];

    function saveRule() {
      const payload: RulePatch = {
        enabled: draft.enabled,
        notify_enabled: draft.notify_enabled,
        severity: draft.severity,
        description: draft.description
      };
      const value = toNumber(draft.threshold_value);
      const min = toNumber(draft.threshold_min);
      const max = toNumber(draft.threshold_max);
      if (value !== null) payload.threshold_value = value;
      if (min !== null) payload.threshold_min = min;
      if (max !== null) payload.threshold_max = max;
      patchMutation.mutate(payload);
    }

    return (
      <article className="notification-card alert-rule-card">
        <div className="alert-rule-topline">
          <div>
            <div className="alert-rule-title-with-help">
              <h3>{rule.name}</h3>
              <InlineHelp
                label={`${rule.name} 說明`}
                content={rule.description ?? "這條規則目前沒有額外說明。"}
              />
            </div>
            <small>{rule.rule_key}</small>
          </div>
          <SeverityBadge severity={draft.severity} />
        </div>
        {guidance ? (
          <div className="alert-rule-help-row">
            <span>規則補充</span>
            <InlineHelp label={`${rule.name} 用途`} content={guidance.usage} />
            <InlineHelp label={`${rule.name} 建議值`} content={guidance.standard} />
            <InlineHelp label={`${rule.name} 目前規則`} content={describeRule(rule, draft)} />
          </div>
        ) : null}
        <div className="alert-rule-meta">
          <span>{rule.metric_source.toUpperCase()}</span>
          <span>{rule.operator}</span>
          <span>{rule.comparison_window}</span>
        </div>
        <div className="alert-rule-switches">
          <button
            className={`alert-rule-toggle ${draft.enabled ? "on" : ""}`}
            onClick={() => setDraft((current) => ({ ...current, enabled: !current.enabled }))}
            type="button"
          >
            {draft.enabled ? <Zap size={14} /> : <BellOff size={14} />}
            {draft.enabled ? "規則啟用" : "規則停用"}
          </button>
          <button
            className={`alert-rule-toggle ${draft.notify_enabled ? "on" : ""}`}
            onClick={() => setDraft((current) => ({ ...current, notify_enabled: !current.notify_enabled }))}
            type="button"
          >
            {draft.notify_enabled ? <Bell size={14} /> : <BellOff size={14} />}
            {draft.notify_enabled ? "可推播" : "不推播"}
          </button>
        </div>
        <label className="alert-rule-field">
          <span>{thresholdLabel}</span>
          {rule.operator === "outside_range" || rule.operator === "between" ? (
            <div className="alert-rule-range-inputs">
              <input value={draft.threshold_min} onChange={(event) => setDraft((current) => ({ ...current, threshold_min: event.target.value }))} />
              <input value={draft.threshold_max} onChange={(event) => setDraft((current) => ({ ...current, threshold_max: event.target.value }))} />
            </div>
          ) : (
            <input value={draft.threshold_value} onChange={(event) => setDraft((current) => ({ ...current, threshold_value: event.target.value }))} />
          )}
        </label>
        <label className="alert-rule-field">
          <span>Severity</span>
          <select value={draft.severity} onChange={(event) => setDraft((current) => ({ ...current, severity: event.target.value as AlertRule["severity"] }))}>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="critical">critical</option>
          </select>
        </label>
        <label className="alert-rule-field">
          <span>說明</span>
          <textarea value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} />
        </label>
        <div className="alert-rule-actions">
          <button className="notification-secondary-button alert-rule-test" disabled={testMutation.isPending} onClick={() => testMutation.mutate()} type="button">
            {testMutation.isPending ? <Loader2 className="spin" size={16} /> : <FlaskConical size={16} />}
            測試規則
          </button>
          <button className="notification-primary-button alert-rule-save" disabled={patchMutation.isPending} onClick={saveRule} type="button">
            {patchMutation.isPending ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
            儲存規則
          </button>
        </div>
        {testMutation.isError ? (
          <div className="alert-rule-test-result error">
            <strong>測試失敗</strong>
            <p>這條規則暫時無法評估，請稍後再試。</p>
          </div>
        ) : latestTest ? (
          <div className={`alert-rule-test-result ${latestTest.data_available === false ? "unavailable" : latestTest.matched ? "matched" : "idle"}`}>
            <div className="alert-rule-test-row">
              <span>最近測試</span>
              <StatusPill matched={latestTest.matched} unavailable={latestTest.data_available === false} />
            </div>
            <div className="alert-rule-test-grid">
              <span>目前值</span>
              <strong>{formatNumber(latestTest.current_value)}</strong>
              <span>通知候選</span>
              <strong>{latestTest.notify_candidate ? "是" : "否"}</strong>
              <span>時間</span>
              <strong>{formatDateTime(latestTest.evaluated_at)}</strong>
            </div>
            <p>{latestTest.reason}</p>
          </div>
        ) : null}
      </article>
    );
  }
}

function RuleSkeleton() {
  return (
    <>
      <div className="notification-skeleton tall" />
      <div className="notification-skeleton tall" />
    </>
  );
}

function SeverityBadge({ severity }: { severity: AlertRule["severity"] }) {
  return <span className={`alert-rule-severity ${severity}`}>{severity}</span>;
}

function StatusPill({ matched, unavailable = false }: { matched: boolean; unavailable?: boolean }) {
  if (unavailable) return <span className="alert-rule-status unavailable">資料暫缺</span>;
  return <span className={`alert-rule-status ${matched ? "matched" : "idle"}`}>{matched ? "命中" : "未命中"}</span>;
}

function toNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumber(value: number | null) {
  if (value === null || value === undefined) return "資料暫缺";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
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

function describeRule(
  rule: AlertRule,
  draft: {
    threshold_value: string;
    threshold_min: string;
    threshold_max: string;
  }
) {
  const value = formatDraftNumber(draft.threshold_value);
  const min = formatDraftNumber(draft.threshold_min);
  const max = formatDraftNumber(draft.threshold_max);
  switch (rule.rule_key) {
    case "twii_pct_move":
      return `TWII 單日變動 <= ${min}% 或 >= ${max}% 時提醒。`;
    case "vix_high":
      return `VIX >= ${value} 時提醒。`;
    case "fear_greed_extreme":
      return `Fear & Greed <= ${min} 或 >= ${max} 時提醒。`;
    case "oil_price_pct_move":
      return `Brent 單日變動 <= ${min}% 或 >= ${max}% 時提醒。`;
    default:
      if (rule.operator === "outside_range" || rule.operator === "between") {
        return `${rule.metric_source.toUpperCase()} ${rule.operator} [${min}, ${max}]。`;
      }
      return `${rule.metric_source.toUpperCase()} ${rule.operator} ${value}。`;
  }
}

function formatDraftNumber(value: string) {
  return value.trim() || "-";
}

function ruleDisplayName(ruleKey: string) {
  const labels: Record<string, string> = {
    twii_pct_move: "TWII 漲跌幅警示",
    vix_high: "VIX 高波動警示",
    fear_greed_extreme: "Fear & Greed 極端警示",
    oil_price_pct_move: "油價單日波動警示"
  };
  return labels[ruleKey] ?? ruleKey;
}

function confidenceLabel(confidence: RecommendationItem["confidence"]) {
  const labels: Record<RecommendationItem["confidence"], string> = {
    low: "低信心",
    medium: "中信心",
    high: "高信心"
  };
  return labels[confidence];
}

function recommendationTypeLabel(type: string) {
  const labels: Record<string, string> = {
    no_action: "暫無調整建議",
    high_dedup_noise: "重複噪音偏高",
    high_trigger_low_delivery: "命中多但送出少",
    too_strict_or_quiet: "規則偏嚴或偏安靜",
    system_issue: "系統 / 資料問題",
    still_tuning: "仍在調校階段"
  };
  return labels[type] ?? type;
}
