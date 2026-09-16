import * as React from "react";

/**
 * Карточка — основная поверхность обоих оформлений.
 */
export interface CardProps extends React.HTMLAttributes<HTMLElement> {
  /** Русское название блока */
  title?: string;
  /** Китайское название — у каждого крупного блока оно есть */
  titleCn?: string;
  /** Служебная надстрочная подпись */
  label?: string;
  /** Кнопка или чип в правом верхнем углу */
  action?: React.ReactNode;
  children?: React.ReactNode;
}

export function Card(props: CardProps): JSX.Element;
