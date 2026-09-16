import React from "react";

export const NAV_ITEMS = [
  { id: "today", label: "Сегодня", cn: "今天", icon: "assets/icons/nav-schedule.png" },
  { id: "rep", label: "REP", cn: "排名", icon: "assets/icons/nav-rating.png" },
  { id: "events", label: "Ивенты", cn: "活动", icon: "assets/icons/nav-tasks.png" },
  { id: "cases", label: "Кейсы", cn: "箱子", icon: "assets/icons/nav-cases.png" },
  { id: "more", label: "Ещё", cn: "更多", icon: "assets/icons/nav-more.png" }
];

/* Нижняя панель: пять разделов, одна настоящая навигация. */
export function BottomNav({ value, onChange, items = NAV_ITEMS, className = "", ...rest }) {
  return (
    <nav className={["zd-dock", className].filter(Boolean).join(" ")} {...rest}>
      {items.map((item) => (
        <button key={item.id} type="button"
          className={item.id === value ? "active" : undefined}
          aria-current={item.id === value ? "page" : undefined}
          onClick={() => onChange && onChange(item.id)}>
          <img src={item.icon} alt="" />
          <small>{item.label}</small>
          <small className="zd-cn">{item.cn}</small>
        </button>
      ))}
    </nav>
  );
}
