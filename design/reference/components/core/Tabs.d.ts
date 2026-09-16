import * as React from "react";

export interface TabItem {
  id: string;
  label: string;
  /** Китайская подпись вкладки */
  cn?: string;
}

/**
 * Вкладки: «Витрина / Моё», «Вид / Помощь», «Идёт сейчас / Позже».
 */
export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  items: TabItem[];
  value: string;
  onChange?: (id: string) => void;
  /** Содержимое активной панели — в Луне рисуется сросшимся с вкладкой */
  panel?: React.ReactNode;
}

export function Tabs(props: TabsProps): JSX.Element;
