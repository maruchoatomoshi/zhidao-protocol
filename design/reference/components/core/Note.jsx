import React from "react";

/* Жёлтая записка: правило игры, оговорка, пометка «пример». */
export function Note({ title, meta, className = "", children, ...rest }) {
  return (
    <aside className={["zd-note", className].filter(Boolean).join(" ")} {...rest}>
      {title && <b>{title}</b>}
      {children}
      {meta && <span>{meta}</span>}
    </aside>
  );
}
