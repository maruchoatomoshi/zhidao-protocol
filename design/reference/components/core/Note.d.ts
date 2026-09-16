import * as React from "react";

/**
 * Записка — жёлтая бумажка с правилом игры или оговоркой к данным.
 */
export interface NoteProps extends React.HTMLAttributes<HTMLElement> {
  title?: string;
  /** Моноширинная подпись снизу: источник данных, дата, «пример» */
  meta?: string;
  children?: React.ReactNode;
}

export function Note(props: NoteProps): JSX.Element;
