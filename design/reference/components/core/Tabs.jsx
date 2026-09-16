import React from "react";

/* Вкладки. В Акве — сегментированная капсула, в Луне — полоска вкладок
   окна свойств: у активной жёлтая полоса сверху, панель сросласть с ней. */
export function Tabs({ items, value, onChange, panel, className = "", ...rest }) {
  return (
    <React.Fragment>
      <div className={["tabs", className].filter(Boolean).join(" ")} role="tablist" {...rest}>
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === value}
            className={item.id === value ? "tab active" : "tab"}
            onClick={() => onChange && onChange(item.id)}
          >
            {item.label}
            {item.cn && <span className="zd-cn"> {item.cn}</span>}
          </button>
        ))}
      </div>
      {panel && <div className="zd-tabpanel" role="tabpanel">{panel}</div>}
    </React.Fragment>
  );
}
