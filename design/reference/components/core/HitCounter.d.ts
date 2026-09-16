import * as React from "react";

/**
 * Счётчик ★ в шапке: чёрные ячейки с поперечной линией, зелёные цифры.
 * Только в шапке — на экранах баланс не повторяется.
 */
export interface HitCounterProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Значение с сервера. null — данных ещё нет, ячейки пустые */
  value?: number | string | null;
  /** Сколько разрядов держать, чтобы счётчик не дёргался */
  digits?: number;
  /** Звезда справа от ячеек */
  star?: boolean;
  /** Разделитель каждые N разрядов */
  groups?: number;
  size?: "md" | "sm";
  label?: string;
}

export function HitCounter(props: HitCounterProps): JSX.Element;
