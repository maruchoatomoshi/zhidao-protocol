import React from "react";

/* Карточка: в Акве — белый градиент со сломом на 50% и радиусом 18,
   в Луне — белая бумага с однопиксельным кантом. */
export function Card({ title, titleCn, label, action, className = "", children, ...rest }) {
  const hasHead = title || label || action;
  return (
    <section className={["glass-card", className].filter(Boolean).join(" ")} {...rest}>
      {hasHead && (
        <header className="zd-card-head">
          <div>
            {label && <span className="zd-label">{label}</span>}
            {title && (
              <h3>
                {title}
                {titleCn && <span className="zd-cn"> {titleCn}</span>}
              </h3>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
