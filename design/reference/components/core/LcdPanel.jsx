import React from "react";

/* Крупная ЖК-поверхность: таймер раунда, показания прибора. Фон свой
   (--surface-lcd), за цифрами стоят погасшие сегменты. Со счётчиком в
   шапке не смешивается: там ячейки, здесь поверхность. */
export function LcdPanel({ value, ghost = "88:88", caption, low, className = "", ...rest }) {
  return (
    <div className={["zd-lcd", low ? "is-low" : "", className].filter(Boolean).join(" ")}
      data-ghost={ghost || undefined} {...rest}>
      <span>{value}</span>
      {caption && <small>{caption}</small>}
    </div>
  );
}
