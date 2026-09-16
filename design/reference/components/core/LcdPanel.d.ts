import * as React from "react";

/**
 * ЖК-поверхность: таймер раунда игры, показания прибора.
 */
export interface LcdPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Показание, обычно ММ:СС */
  value?: React.ReactNode;
  /** Погасшие сегменты за цифрами; формат должен совпадать со значением */
  ghost?: string;
  /** Моноширинная подпись под цифрами */
  caption?: string;
  /** Время на исходе: цифры и кант краснеют */
  low?: boolean;
}

export function LcdPanel(props: LcdPanelProps): JSX.Element;
