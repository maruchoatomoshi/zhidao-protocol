import React from "react";

/* Поле кода: привязка MAX, код комнаты, обмен дублями. Моноширинное,
   с разрядкой — код читают вслух и вводят с чужого экрана. */
export function CodeField({ value = "", onChange, label, hint, error, length = 6, id, className = "", ...rest }) {
  const fieldId = id || React.useId();
  return (
    <div className={className}>
      {label && <label className="zd-label" htmlFor={fieldId}>{label}</label>}
      <input id={fieldId} className="zd-codefield" inputMode="latin" autoComplete="off"
        spellCheck={false} maxLength={length} value={value}
        onChange={(e) => onChange && onChange(e.target.value.toUpperCase().slice(0, length))}
        aria-invalid={error ? true : undefined} {...rest} />
      {error ? <p className="zd-field-error">{error}</p> : hint ? <p className="zd-sub">{hint}</p> : null}
    </div>
  );
}
