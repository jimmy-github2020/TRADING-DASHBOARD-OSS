"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  ChevronDown,
  ChevronsUpDown,
  Loader2,
  Plus,
  Power,
  RefreshCw,
  Trash2,
  X
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { InlineHelp } from "../../components/InlineHelp";
import { MarketAlertRulesPanel } from "../alerts/rules/MarketAlertRulesPanel";

type ApiResponse<T> = {
  data: T;
  meta: Record<string, unknown>;
  timestamp: string;
};

type Strategy = {
  id: string;
  name: string;
  conditions: StrategyConditions;
  is_active: boolean;
  created_at: string;
};

type Signal = {
  id: string;
  symbol: string;
  strategy_id: string;
  strategy_name: string;
  direction: "long" | "short" | "neutral";
  price: number;
  triggered_at: string;
  metadata: Record<string, unknown>;
};

type ScanResult = {
  scanned_symbols: number;
  scanned_strategies: number;
  triggered_signals: number;
  errors: number;
};

type StrategyConditions = {
  logic?: "AND" | "OR";
  direction?: "long" | "short" | "neutral";
  conditions?: BackendCondition[];
  rules?: DraftRule[];
};

type BackendCondition =
  | { type: "rsi"; period: number; operator: NumericOperator; value: number }
  | { type: "macd_cross"; direction: CrossDirection }
  | { type: "ma_cross"; short: number; long: number; direction: CrossDirection }
  | { type: "bollinger_break"; side: "upper" | "lower"; period: number; stddev: number }
  | { type: "kd_cross"; direction: CrossDirection };

type RuleKind =
  | "rsi"
  | "macd_bullish"
  | "macd_bearish"
  | "ma_bullish"
  | "ma_bearish"
  | "bb_upper"
  | "bb_lower"
  | "kd_bullish"
  | "kd_bearish";

type NumericOperator = "<" | ">" | "<=" | ">=";
type CrossDirection = "bullish" | "bearish";

type DraftRule = {
  id: string;
  kind: RuleKind;
  operator: NumericOperator | "triggered";
  value: number;
};

type Toast = {
  id: number;
  tone: "success" | "error";
  message: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";
const strategyQueryKey = ["strategies"];
const signalsQueryKey = ["signals"];

const ruleOptions: Array<{ value: RuleKind; label: string }> = [
  { value: "rsi", label: "RSI(14)" },
  { value: "macd_bullish", label: "MACD 金叉" },
  { value: "macd_bearish", label: "MACD 死叉" },
  { value: "ma_bullish", label: "MA5 上穿 MA20" },
  { value: "ma_bearish", label: "MA5 下穿 MA20" },
  { value: "bb_upper", label: "布林上軌突破" },
  { value: "bb_lower", label: "布林下軌突破" },
  { value: "kd_bullish", label: "KD 黃金交叉" },
  { value: "kd_bearish", label: "KD 死亡交叉" }
];

const eventRuleKinds = new Set<RuleKind>([
  "macd_bullish",
  "macd_bearish",
  "ma_bullish",
  "ma_bearish",
  "bb_upper",
  "bb_lower",
  "kd_bullish",
  "kd_bearish"
]);

export default function StrategiesPage() {
  return (
    <Suspense fallback={<main className="strategy-shell" />}>
      <StrategiesPageContent />
    </Suspense>
  );
}

function StrategiesPageContent() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") === "market" ? "market" : "technical";
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [logic, setLogic] = useState<"AND" | "OR">("AND");
  const [name, setName] = useState("");
  const [rules, setRules] = useState<DraftRule[]>([createRule()]);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const strategiesQuery = useQuery({
    queryKey: strategyQueryKey,
    queryFn: () => fetchJson<ApiResponse<Strategy[]>>("/api/v1/strategies"),
    refetchInterval: 60000
  });

  const signalsQuery = useQuery({
    queryKey: signalsQueryKey,
    queryFn: () => fetchJson<ApiResponse<Signal[]>>("/api/v1/signals?limit=200"),
    refetchInterval: 60000
  });

  const strategies = strategiesQuery.data?.data ?? [];
  const signals = signalsQuery.data?.data ?? [];
  useEffect(() => {
    if (activeTab !== "market" || window.location.hash !== "#market-macro-alerts") return;
    window.requestAnimationFrame(() => {
      document.getElementById("market-macro-alerts")?.scrollIntoView({ block: "start", behavior: "smooth" });
    });
  }, [activeTab]);

  const latestSignalByStrategy = useMemo(() => {
    const map = new Map<string, Signal>();
    for (const signal of signals) {
      if (!map.has(signal.strategy_id)) {
        map.set(signal.strategy_id, signal);
      }
    }
    return map;
  }, [signals]);

  const createMutation = useMutation({
    mutationFn: async () => {
      const cleanName = name.trim();
      if (!cleanName) {
        throw new Error("請輸入策略名稱");
      }
      const conditions = serializeConditions(logic, rules);
      if (conditions.conditions.length === 0) {
        throw new Error("請至少保留一個有效條件");
      }
      return fetchJson<ApiResponse<Strategy>>("/api/v1/strategies", {
        method: "POST",
        body: JSON.stringify({ name: cleanName, conditions })
      });
    },
    onSuccess: () => {
      setName("");
      setLogic("AND");
      setRules([createRule()]);
      showToast("success", "策略已建立");
      queryClient.invalidateQueries({ queryKey: strategyQueryKey });
    },
    onError: (error) => showToast("error", errorMessage(error))
  });

  const activeMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      fetchJson<ApiResponse<Strategy>>(`/api/v1/strategies/${id}/active`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive })
      }),
    onSuccess: () => {
      showToast("success", "策略狀態已更新");
      queryClient.invalidateQueries({ queryKey: strategyQueryKey });
    },
    onError: (error) => showToast("error", errorMessage(error))
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      fetchJson<ApiResponse<{ id: string }>>(`/api/v1/strategies/${id}`, {
        method: "DELETE"
      }),
    onSuccess: () => {
      showToast("success", "策略已刪除");
      queryClient.invalidateQueries({ queryKey: strategyQueryKey });
      queryClient.invalidateQueries({ queryKey: signalsQueryKey });
    },
    onError: (error) => showToast("error", errorMessage(error))
  });

  const scanMutation = useMutation({
    mutationFn: () =>
      fetchJson<ApiResponse<ScanResult>>("/api/v1/signals/scan", {
        method: "POST"
      }),
    onSuccess: (response) => {
      const result = response.data;
      showToast(
        result.errors > 0 ? "error" : "success",
        `掃描完成：${result.scanned_symbols} symbols，${result.triggered_signals} signals，${result.errors} errors`
      );
      queryClient.invalidateQueries({ queryKey: signalsQueryKey });
    },
    onError: (error) => showToast("error", errorMessage(error))
  });

  function showToast(tone: Toast["tone"], message: string) {
    const id = Date.now();
    setToasts((current) => [...current, { id, tone, message }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 3000);
  }

  function updateRule(id: string, patch: Partial<DraftRule>) {
    setRules((current) =>
      current.map((rule) => {
        if (rule.id !== id) return rule;
        const next = { ...rule, ...patch };
        if (patch.kind && eventRuleKinds.has(patch.kind)) {
          next.operator = "triggered";
        }
        if (patch.kind === "rsi" && next.operator === "triggered") {
          next.operator = "<";
        }
        return next;
      })
    );
  }

  return (
    <main className="strategy-shell strategy-center-shell">
      <header className="strategy-header strategy-center-header">
        <div>
          <p className="panel-kicker">RULE CENTER</p>
          <div className="strategy-heading-with-help">
            <h1>策略中心</h1>
            <InlineHelp
              label="策略中心說明"
              content="技術策略在這裡建立，市場與宏觀警示也在同一個入口管理；通知是否送出仍由通知設定控制。"
            />
          </div>
          <span>技術策略與市場警示集中管理。</span>
        </div>
        {activeTab === "technical" ? (
          <button className="primary-action" onClick={() => scanMutation.mutate()} disabled={scanMutation.isPending}>
            {scanMutation.isPending ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            立即掃描
          </button>
        ) : null}
      </header>

      <nav className="strategy-center-tabs" aria-label="策略中心分頁">
        <Link className={activeTab === "technical" ? "active" : ""} href="/strategies?tab=technical">
          技術策略
        </Link>
        <Link className={activeTab === "market" ? "active" : ""} href="/strategies?tab=market">
          市場 / 宏觀警示
        </Link>
      </nav>

      <section className="strategy-center-note">
        <Link className="strategy-center-note-card clickable" href="/strategies?tab=technical">
          <span className="strategy-center-note-title">
            <strong>技術策略</strong>
          </span>
          <small>前往技術策略</small>
        </Link>
        <Link className="strategy-center-note-card clickable" href="/strategies?tab=market#market-macro-alerts">
          <span className="strategy-center-note-title">
            <strong>市場 / 宏觀警示</strong>
          </span>
          <small>前往市場警示</small>
        </Link>
        <div className="strategy-center-note-card">
          <span className="strategy-center-note-title">
            <strong>推播與結果</strong>
            <InlineHelp
              label="推播與結果說明"
              content="通知是否送出由通知設定頁控制；執行結果與原因可到通知診斷頁查看。"
            />
          </span>
        </div>
      </section>

      {activeTab === "market" ? (
        <MarketAlertRulesPanel compact showHero={false} />
      ) : (
      <section className="strategy-layout">
        <section className="strategy-list-panel">
          <div className="panel-header strategy-panel-header">
            <div>
              <h2>策略清單</h2>
              <span>{strategies.length} strategies</span>
            </div>
          </div>

          {strategiesQuery.isLoading ? <StrategySkeleton /> : null}
          {strategiesQuery.isError ? <ErrorState message={errorMessage(strategiesQuery.error)} /> : null}
          {!strategiesQuery.isLoading && !strategiesQuery.isError && strategies.length === 0 ? (
            <EmptyStrategies onAdd={() => document.getElementById("strategy-name")?.focus()} />
          ) : null}

          <div className="strategy-list">
            {strategies.map((strategy) => {
              const latest = latestSignalByStrategy.get(strategy.id);
              const strategySignals = signals.filter((signal) => signal.strategy_id === strategy.id).slice(0, 10);
              const expanded = expandedId === strategy.id;
              return (
                <article className={`strategy-row-card ${expanded ? "expanded" : ""}`} key={strategy.id}>
                  <button
                    className="strategy-row-main"
                    onClick={() => setExpandedId(expanded ? null : strategy.id)}
                    aria-expanded={expanded}
                  >
                    <div className="strategy-name-block">
                      <strong>{strategy.name}</strong>
                      <span>{summarizeConditions(strategy.conditions)}</span>
                    </div>
                    <div className="strategy-meta">
                      <span>{latest ? formatDateTime(latest.triggered_at) : "尚無觸發"}</span>
                      <ChevronDown className={expanded ? "rotated" : ""} size={18} />
                    </div>
                  </button>

                  <div className="strategy-actions">
                    <button
                      className={`toggle-button ${strategy.is_active ? "on" : ""}`}
                      onClick={() => activeMutation.mutate({ id: strategy.id, isActive: !strategy.is_active })}
                      disabled={activeMutation.isPending}
                      aria-label={strategy.is_active ? "停用策略" : "啟用策略"}
                    >
                      <Power size={15} />
                      {strategy.is_active ? "啟用" : "停用"}
                    </button>
                    <button
                      className="danger-action"
                      onClick={() => {
                        if (window.confirm(`確定刪除策略「${strategy.name}」？`)) {
                          deleteMutation.mutate(strategy.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      aria-label="刪除策略"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>

                  {expanded ? (
                    <div className="signal-table-wrap">
                      {strategySignals.length > 0 ? (
                        <table className="signal-table">
                          <thead>
                            <tr>
                              <th>Symbol</th>
                              <th>Direction</th>
                              <th>Price</th>
                              <th>Triggered</th>
                            </tr>
                          </thead>
                          <tbody>
                            {strategySignals.map((signal) => (
                              <tr key={signal.id}>
                                <td>{signal.symbol}</td>
                                <td>{signal.direction}</td>
                                <td>{formatNumber(signal.price)}</td>
                                <td>{formatDateTime(signal.triggered_at)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className="inline-empty">這個策略目前沒有 signals。</div>
                      )}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>

        <aside className="strategy-editor-panel">
          <div className="panel-header strategy-panel-header">
            <div>
              <h2>新增策略</h2>
              <span>視覺化條件組合</span>
            </div>
          </div>

          <form
            className="strategy-form"
            onSubmit={(event) => {
              event.preventDefault();
              createMutation.mutate();
            }}
          >
            <label className="field-block">
              <span>策略名稱</span>
              <input
                id="strategy-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="例：RSI 超賣 + MACD 金叉"
              />
            </label>

            <div className="logic-switch" aria-label="條件邏輯">
              {(["AND", "OR"] as const).map((item) => (
                <button
                  className={logic === item ? "selected" : ""}
                  key={item}
                  type="button"
                  onClick={() => setLogic(item)}
                >
                  {item}
                </button>
              ))}
            </div>

            <div className="rule-stack">
              {rules.map((rule, index) => (
                <div className="rule-card" key={rule.id}>
                  <div className="rule-grip" aria-hidden="true">
                    <ChevronsUpDown size={16} />
                  </div>
                  <label>
                    <span>指標</span>
                    <select
                      value={rule.kind}
                      onChange={(event) => updateRule(rule.id, { kind: event.target.value as RuleKind })}
                    >
                      {ruleOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>運算子</span>
                    <select
                      value={eventRuleKinds.has(rule.kind) ? "triggered" : rule.operator}
                      disabled={eventRuleKinds.has(rule.kind)}
                      onChange={(event) =>
                        updateRule(rule.id, { operator: event.target.value as NumericOperator | "triggered" })
                      }
                    >
                      {eventRuleKinds.has(rule.kind) ? (
                        <option value="triggered">發生</option>
                      ) : (
                        <>
                          <option value="<">&lt;</option>
                          <option value=">">&gt;</option>
                          <option value="<=">&lt;=</option>
                          <option value=">=">&gt;=</option>
                        </>
                      )}
                    </select>
                  </label>
                  <label>
                    <span>數值</span>
                    <input
                      type="number"
                      value={eventRuleKinds.has(rule.kind) ? "" : rule.value}
                      disabled={eventRuleKinds.has(rule.kind)}
                      min={0}
                      max={100}
                      step={1}
                      onChange={(event) => updateRule(rule.id, { value: Number(event.target.value) })}
                      placeholder={eventRuleKinds.has(rule.kind) ? "-" : "30"}
                    />
                  </label>
                  <button
                    className="remove-rule"
                    type="button"
                    onClick={() => setRules((current) => current.filter((item) => item.id !== rule.id))}
                    disabled={rules.length === 1}
                    aria-label={`刪除條件 ${index + 1}`}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>

            <button className="secondary-action" type="button" onClick={() => setRules((current) => [...current, createRule()])}>
              <Plus size={16} />
              新增條件
            </button>

            <button className="primary-action full-width" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? <Loader2 className="spin" size={16} /> : <Activity size={16} />}
              儲存策略
            </button>
          </form>
        </aside>
      </section>
      )}

      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <div className={`toast ${toast.tone}`} key={toast.id}>
            {toast.tone === "error" ? <AlertCircle size={16} /> : <Activity size={16} />}
            {toast.message}
          </div>
        ))}
      </div>
    </main>
  );
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${path} HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function createRule(): DraftRule {
  return {
    id: crypto.randomUUID(),
    kind: "rsi",
    operator: "<",
    value: 30
  };
}

function serializeConditions(logic: "AND" | "OR", rules: DraftRule[]): Required<Pick<StrategyConditions, "logic" | "direction" | "conditions">> {
  return {
    logic,
    direction: "neutral",
    conditions: rules.map(ruleToBackendCondition)
  };
}

function ruleToBackendCondition(rule: DraftRule): BackendCondition {
  switch (rule.kind) {
    case "rsi":
      return { type: "rsi", period: 14, operator: rule.operator as NumericOperator, value: Number(rule.value) };
    case "macd_bullish":
      return { type: "macd_cross", direction: "bullish" };
    case "macd_bearish":
      return { type: "macd_cross", direction: "bearish" };
    case "ma_bullish":
      return { type: "ma_cross", short: 5, long: 20, direction: "bullish" };
    case "ma_bearish":
      return { type: "ma_cross", short: 5, long: 20, direction: "bearish" };
    case "bb_upper":
      return { type: "bollinger_break", side: "upper", period: 20, stddev: 2 };
    case "bb_lower":
      return { type: "bollinger_break", side: "lower", period: 20, stddev: 2 };
    case "kd_bullish":
      return { type: "kd_cross", direction: "bullish" };
    case "kd_bearish":
      return { type: "kd_cross", direction: "bearish" };
  }
}

function summarizeConditions(conditions: StrategyConditions) {
  const logic = conditions.logic ?? "AND";
  const backendConditions = conditions.conditions ?? normalizeRules(conditions.rules ?? []);
  if (backendConditions.length === 0) return "尚未設定條件";
  return backendConditions.map(describeCondition).join(` ${logic} `);
}

function normalizeRules(rules: DraftRule[]): BackendCondition[] {
  return rules.map((rule) => ruleToBackendCondition(rule));
}

function describeCondition(condition: BackendCondition) {
  switch (condition.type) {
    case "rsi":
      return `RSI(${condition.period}) ${condition.operator} ${condition.value}`;
    case "macd_cross":
      return condition.direction === "bullish" ? "MACD 金叉" : "MACD 死叉";
    case "ma_cross":
      return `MA${condition.short} ${condition.direction === "bullish" ? "上穿" : "下穿"} MA${condition.long}`;
    case "bollinger_break":
      return condition.side === "upper" ? "布林上軌突破" : "布林下軌突破";
    case "kd_cross":
      return condition.direction === "bullish" ? "KD 黃金交叉" : "KD 死亡交叉";
  }
}

function StrategySkeleton() {
  return (
    <div className="strategy-list">
      {[0, 1, 2].map((item) => (
        <div className="strategy-skeleton" key={item}>
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="strategy-error">
      <AlertCircle size={18} />
      {message}
    </div>
  );
}

function EmptyStrategies({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="strategy-empty">
      <Activity size={24} />
      <strong>尚無策略</strong>
      <span>建立第一個條件組合後，就能執行掃描並追蹤觸發紀錄。</span>
      <button className="secondary-action" type="button" onClick={onAdd}>
        <Plus size={16} />
        新增策略
      </button>
    </div>
  );
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

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Math.abs(value) > 1000 ? 2 : 4
  }).format(value);
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "操作失敗";
}
