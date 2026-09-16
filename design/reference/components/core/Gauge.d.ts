import * as React from "react";

/**
 * Прибор: полоса прогресса или счётные сегменты (попытки сканера).
 */
export interface GaugeProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number;
  max?: number;
  /** Счётный вариант: сколько всего сегментов */
  segments?: number;
  label?: string;
}

export function Gauge(props: GaugeProps): JSX.Element;
