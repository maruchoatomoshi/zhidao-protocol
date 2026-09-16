import * as React from "react";

/**
 * Плитка раздела в «Ещё» — кнопка в пропорциях 88×31.
 */
export interface HubTileProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  name: string;
  /** Китайское название раздела — обязательно */
  nameCn: string;
}

export function HubTile(props: HubTileProps): JSX.Element;
