import React from "react";
import { HitCounter } from "../core/HitCounter.jsx";

/* Шапка: логотип, счётчик ★ и кнопка профиля. Баланс живёт только здесь —
   на экранах он не повторяется. */
export function AppHeader({
  logo = "assets/zhidao-dragon-logo-256.png",
  title = "ZHIDAO",
  subtitle = "PROTOCOL · HAINAN",
  stars = null,
  digits = 4,
  onProfile,
  profileLabel = "Профиль",
  className = "",
  ...rest
}) {
  return (
    <header className={["zd-header", className].filter(Boolean).join(" ")} {...rest}>
      <div className="zd-brand">
        <img src={logo} alt="" />
        <span>
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
      </div>
      <HitCounter value={stars} digits={digits} size="sm" />
      <button type="button" className="zd-profile-fab" onClick={onProfile} aria-label={profileLabel}>
        我
      </button>
    </header>
  );
}
