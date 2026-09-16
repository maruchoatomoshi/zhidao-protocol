import React from "react";

/* Кнопка. Четыре яруса материала в Акве, скос окна в Луне.
   variant="confirm" — «подтверди вторым касанием»: первое касание переводит
   кнопку в янтарное состояние is-armed и меняет подпись, второе выполняет.
   Красной кнопки в приложении нет: красный носит только шильдик системного
   администратора. */
export function Button({
  variant = "secondary",
  confirmLabel = "Точно?",
  onClick,
  disabled,
  type = "button",
  className = "",
  children,
  ...rest
}) {
  const [armed, setArmed] = React.useState(false);
  const isConfirm = variant === "confirm";
  const cls = [
    "btn",
    isConfirm ? "btn-secondary" : "btn-" + variant,
    isConfirm && armed ? "is-armed" : "",
    className
  ].filter(Boolean).join(" ");

  function handle(event) {
    if (!isConfirm) return onClick && onClick(event);
    if (!armed) return setArmed(true);
    setArmed(false);
    if (onClick) onClick(event);
  }

  return (
    <button
      type={type}
      className={cls}
      disabled={disabled}
      onClick={handle}
      onBlur={isConfirm ? () => setArmed(false) : undefined}
      {...rest}
    >
      <span>{armed ? confirmLabel : children}</span>
    </button>
  );
}
