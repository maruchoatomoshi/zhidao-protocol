import React from "react";

/* Таблица с шапкой колонок и выбранной строкой. В Луне выбранная строка
   синяя (#316ac5), в Акве — цвет акцента. */
export function DataTable({ columns, rows, selectedId, onSelect, className = "", ...rest }) {
  return (
    <table className={["zd-table", className].filter(Boolean).join(" ")} {...rest}>
      <thead>
        <tr>
          {columns.map((col) => (
            <th key={col.key} style={col.width ? { width: col.width } : undefined}>{col.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.id}
            aria-selected={row.id === selectedId}
            onClick={onSelect ? () => onSelect(row.id) : undefined}
          >
            {columns.map((col) => (
              <td key={col.key}>{row[col.key]}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
