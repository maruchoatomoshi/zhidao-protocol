import * as React from "react";

/**
 * Кнопка ZHIDAO: главная, обычная, системная, действие и «подтверди вторым
 * касанием». Зона нажатия не меньше 44 px.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary — главная, secondary — обычная, system — служебная (хром/Tahoma),
   *  action — лаймовое действие, confirm — подтверждение вторым касанием */
  variant?: "primary" | "secondary" | "system" | "action" | "confirm";
  /** Подпись во взведённом состоянии: «Точно? −30★» */
  confirmLabel?: string;
  children?: React.ReactNode;
}

export function Button(props: ButtonProps): JSX.Element;
