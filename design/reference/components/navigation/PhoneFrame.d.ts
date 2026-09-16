import * as React from "react";

/**
 * Артборд телефона 390×844 с оформлением и темой. Один экран — один артборд.
 */
export interface PhoneFrameProps extends React.HTMLAttributes<HTMLDivElement> {
  /** "aqua" — Аква, "luna" — Луна-Аква */
  skin?: "aqua" | "luna" | "xp";
  theme?: "light" | "dark";
  /** "full" — движение умеренное, "none" — вариант без анимации */
  motion?: "full" | "none";
  header?: React.ReactNode;
  nav?: React.ReactNode;
  /** Подпись артборда для комментариев и сдачи */
  label?: string;
}

export function PhoneFrame(props: PhoneFrameProps): JSX.Element;
