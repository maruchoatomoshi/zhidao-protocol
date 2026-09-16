import React from "react";

/* Строка состояния внизу окна: только факты — источник данных, режим,
   связь. Обещаний здесь не бывает. */
export function StatusBar({ items = [], className = "", ...rest }) {
  return (
    <footer className={["zd-statusbar", className].filter(Boolean).join(" ")} {...rest}>
      {items.map((item, i) => (
        <span key={i}>{item}</span>
      ))}
    </footer>
  );
}
