import React from "react";

/* Счётчик в шапке: по ячейке на разряд, поперечная линия по середине —
   счётчик посещений нулевых. Живёт только в шапке; крупные показания игр
   рисует LcdPanel, у него другой фон. */
export function HitCounter({ value, digits = 4, star = true, groups, size = "md", className = "", label = "★", ...rest }) {
  const text = value === null || value === undefined ? "" : String(value);
  const cells = text.padStart(digits, " ").slice(-digits).split("");
  const out = [];
  cells.forEach((ch, i) => {
    if (groups && i > 0 && (cells.length - i) % groups === 0) out.push(<i key={"s" + i}>·</i>);
    out.push(<b key={i}>{ch === " " ? "\u00a0" : ch}</b>);
  });
  const cls = ["hit-counter", star ? "hit-counter-star" : "", size === "sm" ? "hit-counter-sm" : "", className]
    .filter(Boolean).join(" ");
  return <span className={cls} aria-label={label + " " + text} {...rest}>{out}</span>;
}
