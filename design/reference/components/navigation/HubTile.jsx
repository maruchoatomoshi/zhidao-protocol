import React from "react";

/* Плитка раздела в «Ещё»: пропорции кнопки 88×31, спокойные цвета темы. */
export function HubTile({ name, nameCn, disabled, onClick, className = "", ...rest }) {
  return (
    <button type="button" className={["hub-tile", className].filter(Boolean).join(" ")}
      disabled={disabled} onClick={onClick} {...rest}>
      <span className="hub-name">{name}</span>
      <span className="hub-cn">{nameCn}</span>
    </button>
  );
}
