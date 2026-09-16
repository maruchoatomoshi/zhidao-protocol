import React from "react";

/* Выпадающий список. В Луне — поле окна свойств с кнопкой-стрелкой. */
export function Select({ value, onChange, options = [], label, disabled, id, className = "", ...rest }) {
  const selectId = id || React.useId();
  return (
    <div className={className}>
      {label && <label className="zd-label" htmlFor={selectId}>{label}</label>}
      <span className="zd-select">
        <select id={selectId} value={value} disabled={disabled}
          onChange={(e) => onChange && onChange(e.target.value)} {...rest}>
          {options.map((opt) => (
            <option value={opt.value} key={opt.value}>{opt.label}</option>
          ))}
        </select>
      </span>
    </div>
  );
}
