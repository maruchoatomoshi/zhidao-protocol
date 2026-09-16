import * as React from "react";

/**
 * Поле кода — привязка MAX, код комнаты, код обмена.
 */
export interface CodeFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  value?: string;
  onChange?: (next: string) => void;
  label?: string;
  hint?: string;
  /** Текст ошибки от сервера, например «аккаунт уже привязан к другому MAX» */
  error?: string;
  /** Длина кода, по умолчанию 6 */
  length?: number;
}

export function CodeField(props: CodeFieldProps): JSX.Element;
