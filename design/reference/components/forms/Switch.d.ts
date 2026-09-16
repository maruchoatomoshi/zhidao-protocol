import * as React from "react";

/**
 * Переключатель настройки: оформление, ночная тема, «Анимации».
 */
export interface SwitchProps extends React.HTMLAttributes<HTMLLabelElement> {
  checked?: boolean;
  onChange?: (next: boolean) => void;
  label?: string;
  /** Китайская подпись */
  labelCn?: string;
  /** Пояснение под подписью */
  hint?: string;
  disabled?: boolean;
}

export function Switch(props: SwitchProps): JSX.Element;
