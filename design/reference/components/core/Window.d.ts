import * as React from "react";

/**
 * Окно с заголовком — оболочка экрана игры, профиля, кейсов и диалогов.
 */
export interface WindowProps extends React.HTMLAttributes<HTMLElement> {
  title: string;
  /** Китайское название раздела */
  titleCn?: string;
  /** Путь к значку 23×23 из assets/icons */
  icon?: string;
  /** Служебная подпись справа в заголовке */
  meta?: string;
  /** <StatusBar>: рисуется под телом окна */
  status?: React.ReactNode;
  children?: React.ReactNode;
}

export function Window(props: WindowProps): JSX.Element;
