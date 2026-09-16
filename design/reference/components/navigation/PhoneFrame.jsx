import React from "react";

/* Артборд 390×844 с выбранным оформлением и темой. Строку состояния
   телефона и клавиатуру не рисуем; сверху остаётся место под панель MAX. */
export function PhoneFrame({
  skin = "aqua",
  theme = "light",
  motion = "full",
  header,
  nav,
  label,
  className = "",
  children,
  ...rest
}) {
  return (
    <div className={["zd", "zd-phone", className].filter(Boolean).join(" ")}
      data-design={skin === "luna" || skin === "xp" ? "xp" : "aqua"}
      data-theme={theme === "dark" ? "dark" : undefined}
      data-motion={motion}
      data-screen-label={label}
      {...rest}>
      <div className="zd-max-hint" aria-hidden="true" />
      {header}
      <div className="zd-phone-scroll">{children}</div>
      {nav}
    </div>
  );
}
