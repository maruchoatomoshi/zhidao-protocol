import React from "react";

/* Пустое состояние: нет связи, сезон не начался, ничего не куплено,
   пустая коллекция. Причина словами, одно действие при необходимости. */
export function EmptyState({ title, children, action, className = "", ...rest }) {
  return (
    <div className={["zd-empty", className].filter(Boolean).join(" ")} {...rest}>
      {title && <strong>{title}</strong>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
