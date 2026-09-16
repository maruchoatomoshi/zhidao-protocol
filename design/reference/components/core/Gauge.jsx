import React from "react";

/* Прибор: жёлоб продавлен внутрь, заполнение выпуклое. Сегментный вариант —
   для счётного прогресса (три попытки из пяти). Пустой прибор показывает
   насечки, а не притворяется полным. */
export function Gauge({ value = 0, max = 100, segments, label, className = "", ...rest }) {
  if (segments) {
    const on = Math.max(0, Math.min(segments, Math.round(value)));
    return (
      <div className={["gauge-segments", className].filter(Boolean).join(" ")}
        role="meter" aria-valuenow={on} aria-valuemax={segments} aria-label={label} {...rest}>
        {Array.from({ length: segments }, (_, i) => (
          <i className={i < on ? "gauge-seg is-on" : "gauge-seg"} key={i} />
        ))}
      </div>
    );
  }
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className={["gauge", pct === 0 ? "is-empty" : "", className].filter(Boolean).join(" ")}
      role="meter" aria-valuenow={value} aria-valuemax={max} aria-label={label} {...rest}>
      {pct > 0 && <div className="gauge-fill" style={{ width: pct + "%" }} />}
    </div>
  );
}
