type FearGreedGaugeProps = {
  value?: number | null;
  label?: string;
};

type GaugeBand = {
  min: number;
  max: number;
  label: string;
  color: string;
};

const bands: GaugeBand[] = [
  { min: 0, max: 25, label: "Extreme Fear", color: "#ef4444" },
  { min: 26, max: 45, label: "Fear", color: "#f97316" },
  { min: 46, max: 55, label: "Neutral", color: "#facc15" },
  { min: 56, max: 75, label: "Greed", color: "#86efac" },
  { min: 76, max: 100, label: "Extreme Greed", color: "#22c55e" },
];

function clampGaugeValue(value: number) {
  return Math.min(Math.max(value, 0), 100);
}

function getBand(value: number) {
  return bands.find((band) => value >= band.min && value <= band.max) ?? bands[2];
}

function pointOnArc(centerX: number, centerY: number, radius: number, angle: number) {
  const radians = (angle * Math.PI) / 180;
  return {
    x: centerX + radius * Math.cos(radians),
    y: centerY - radius * Math.sin(radians),
  };
}

function valueToAngle(value: number) {
  return 180 - (clampGaugeValue(value) / 100) * 180;
}

function arcPath(startValue: number, endValue: number) {
  const start = pointOnArc(110, 110, 82, valueToAngle(startValue));
  const end = pointOnArc(110, 110, 82, valueToAngle(endValue));
  const largeArcFlag = Math.abs(valueToAngle(endValue) - valueToAngle(startValue)) > 180 ? 1 : 0;
  return `M ${start.x.toFixed(3)} ${start.y.toFixed(3)} A 82 82 0 ${largeArcFlag} 1 ${end.x.toFixed(3)} ${end.y.toFixed(3)}`;
}

export function FearGreedGauge({ value, label }: FearGreedGaugeProps) {
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const normalizedValue = hasValue ? clampGaugeValue(value) : null;
  const activeBand = normalizedValue === null ? null : getBand(normalizedValue);
  const needleAngle = normalizedValue === null ? 90 : valueToAngle(normalizedValue);
  const needleEnd = pointOnArc(110, 110, 64, needleAngle);

  return (
    <div
      aria-label={hasValue ? `Fear and Greed ${normalizedValue}` : "Fear and Greed data unavailable"}
      style={{
        border: "1px solid var(--border-soft)",
        borderRadius: 12,
        background: "var(--panel)",
        padding: 16,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
        <div>
          <span style={{ color: "var(--muted-2)", fontSize: "var(--text-xs)", fontWeight: 800 }}>
            Fear & Greed
          </span>
          <strong style={{ color: "var(--text)", display: "block", fontSize: 18, marginTop: 3 }}>
            {label ?? activeBand?.label ?? "資料暫缺"}
          </strong>
        </div>
        <strong
          style={{
            color: activeBand?.color ?? "var(--muted)",
            fontSize: 30,
            lineHeight: 1,
          }}
        >
          {normalizedValue ?? "—"}
        </strong>
      </div>

      <svg role="img" viewBox="0 0 220 136" width="100%" aria-hidden="true">
        <path d={arcPath(0, 100)} fill="none" stroke="var(--border-soft)" strokeLinecap="round" strokeWidth="16" />
        {bands.map((band) => (
          <path
            d={arcPath(band.min, band.max)}
            fill="none"
            key={band.label}
            opacity={normalizedValue === null || activeBand?.label === band.label ? 1 : 0.34}
            stroke={band.color}
            strokeLinecap="round"
            strokeWidth="16"
          />
        ))}
        {normalizedValue !== null ? (
          <>
            <line
              stroke={activeBand?.color ?? "var(--accent)"}
              strokeLinecap="round"
              strokeWidth="4"
              x1="110"
              x2={needleEnd.x}
              y1="110"
              y2={needleEnd.y}
            />
            <circle cx="110" cy="110" fill="var(--panel-2)" r="8" stroke={activeBand?.color} strokeWidth="3" />
          </>
        ) : null}
        <text fill="var(--muted-2)" fontSize="11" x="24" y="126">
          Fear
        </text>
        <text fill="var(--muted-2)" fontSize="11" textAnchor="end" x="196" y="126">
          Greed
        </text>
      </svg>

      {!hasValue ? (
        <div style={{ color: "var(--muted)", fontSize: "var(--text-sm)", marginTop: 8 }}>資料暫缺</div>
      ) : (
        <div style={{ color: "var(--muted-2)", display: "flex", fontSize: 11, justifyContent: "space-between" }}>
          <span>Extreme Fear</span>
          <span>Neutral</span>
          <span>Extreme Greed</span>
        </div>
      )}
    </div>
  );
}
