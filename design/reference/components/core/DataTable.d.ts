import * as React from "react";

export interface TableColumn {
  key: string;
  label: string;
  width?: string | number;
}

export interface TableRow {
  id: string;
  [key: string]: React.ReactNode;
}

/**
 * Таблица с шапкой колонок и выбранной строкой — витрина магазина и
 * списки консоли вожатого в оформлении «Луна-Аква».
 */
export interface DataTableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  columns: TableColumn[];
  rows: TableRow[];
  selectedId?: string;
  onSelect?: (id: string) => void;
}

export function DataTable(props: DataTableProps): JSX.Element;
