import React from "react";

/* Флажок. В Луне — квадрат окна свойств с зелёной галочкой. */
export function Checkbox({ checked, onChange, label, labelCn, disabled, className = "", ...rest }) {
  return (
    <label className={["zd-check", className].filter(Boolean).join(" ")} {...rest}>
      <input type="checkbox" checked={!!checked} disabled={disabled}
        onChange={(e) => onChange && onChange(e.target.checked)} />
      <span>
        {label}
        {labelCn && <small className="zd-cn"> {labelCn}</small>}
      </span>
    </label>
  );
}
