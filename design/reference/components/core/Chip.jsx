import React from "react";

/* Чипы и отметки: «награда», «дубль · обмен», «пример». */
export function Chip({ tone = "default", dot, className = "", children, ...rest }) {
  const map = { reward: "chip-reward", dupe: "chip-dupe", example: "chip-example" };
  return (
    <span className={["chip", map[tone] || "", className].filter(Boolean).join(" ")} {...rest}>
      {dot && <i />}
      {children}
    </span>
  );
}
