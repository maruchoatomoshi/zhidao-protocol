import * as React from "react";

/**
 * Шапка приложения: логотип, табло ★, кнопка профиля.
 */
export interface AppHeaderProps extends React.HTMLAttributes<HTMLElement> {
  logo?: string;
  title?: string;
  subtitle?: string;
  /** Баланс ★ с сервера; null — данных нет */
  stars?: number | null;
  digits?: number;
  onProfile?: () => void;
  profileLabel?: string;
}

export function AppHeader(props: AppHeaderProps): JSX.Element;
