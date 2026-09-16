import * as React from "react";

/**
 * Строка состояния — нижняя полоса окна с фактами о данных и режиме.
 */
export interface StatusBarProps extends React.HTMLAttributes<HTMLElement> {
  /** Ячейки слева направо, разделяются кантом */
  items?: React.ReactNode[];
}

export function StatusBar(props: StatusBarProps): JSX.Element;
