import * as React from "react";

export interface NavItem {
  id: string;
  label: string;
  cn: string;
  icon: string;
}

/**
 * Нижняя панель: Сегодня 今天, REP 排名, Ивенты 活动, Кейсы 箱子, Ещё 更多.
 */
export interface BottomNavProps extends React.HTMLAttributes<HTMLElement> {
  value?: string;
  onChange?: (id: string) => void;
  items?: NavItem[];
}

export const NAV_ITEMS: NavItem[];
export function BottomNav(props: BottomNavProps): JSX.Element;
