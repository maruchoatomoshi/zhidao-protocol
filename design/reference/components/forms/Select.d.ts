import * as React from "react";

export interface SelectOption { value: string; label: string }

/** Выпадающий список окна свойств. */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  value?: string;
  onChange?: (next: string) => void;
  options?: SelectOption[];
  label?: string;
}

export function Select(props: SelectProps): JSX.Element;
