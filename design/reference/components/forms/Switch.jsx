import React from "react";

/* Переключатель. В Акве — тумблер из цветного пластика, в Луне —
   радиокнопка окна свойств. Разметка одна, вещество разное. */
export function Switch({ checked, onChange, label, labelCn, hint, disabled, className = "", ...rest }) {
  return (
    <label className={["zd-switch", className].filter(Boolean).join(" ")}
      role="switch" aria-checked={!!checked} aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) => {
        if (disabled || (e.key !== " " && e.key !== "Enter")) return;
        e.preventDefault();
        onChange && onChange(!checked);
      }}
      onClick={() => !disabled && onChange && onChange(!checked)}
      {...rest}>
      <i />
      <span>
        {label}
        {labelCn && <small className="zd-cn"> {labelCn}</small>}
        {hint && <small className="zd-sub" style={{ display: "block" }}>{hint}</small>}
      </span>
    </label>
  );
}
