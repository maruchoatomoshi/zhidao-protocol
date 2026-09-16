import * as React from "react";

/**
 * Чип-отметка: награда, дубль, пример, статус.
 */
export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** default — служебная, reward — награда, dupe — «дубль · обмен», example — «пример» */
  tone?: "default" | "reward" | "dupe" | "example";
  /** Зелёная точка «идёт сейчас» */
  dot?: boolean;
  children?: React.ReactNode;
}

export function Chip(props: ChipProps): JSX.Element;
