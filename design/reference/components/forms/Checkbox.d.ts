import * as React from "react";

/** Флажок окна свойств. */
export interface CheckboxProps extends React.HTMLAttributes<HTMLLabelElement> {
  checked?: boolean;
  onChange?: (next: boolean) => void;
  label?: string;
  labelCn?: string;
  disabled?: boolean;
}

export function Checkbox(props: CheckboxProps): JSX.Element;
