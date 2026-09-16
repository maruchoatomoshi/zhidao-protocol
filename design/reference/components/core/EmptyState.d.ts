import * as React from "react";

/**
 * Пустое состояние — честная причина пустоты вместо заглушек и скелетонов.
 */
export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  /** Одна кнопка, если действие вообще есть */
  action?: React.ReactNode;
  children?: React.ReactNode;
}

export function EmptyState(props: EmptyStateProps): JSX.Element;
