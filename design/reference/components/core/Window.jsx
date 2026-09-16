import React from "react";

/* Окно с заголовком. В Луне это окно рабочего стола нулевых, в Акве —
   стеклянная панель с той же полосой заголовка. Строка состояния внизу
   передаётся через status. */
export function Window({ title, titleCn, icon, meta, status, className = "", children, ...rest }) {
  return (
    <section className={["zd-window", className].filter(Boolean).join(" ")} {...rest}>
      <header className="zd-titlebar">
        {icon && <img src={icon} alt="" />}
        <h2>{title}</h2>
        {titleCn && <span className="zd-cn">{titleCn}</span>}
        {meta && <span>{meta}</span>}
      </header>
      <div className="zd-window-body">{children}</div>
      {status}
    </section>
  );
}
