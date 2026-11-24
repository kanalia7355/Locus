import type { ReactNode, Ref } from "react";

export function IconButton({
  label,
  onClick,
  children,
  disabled = false,
  buttonRef,
  type = "button",
  ...rest
}: {
  label: string;
  onClick?: () => void;
  children: ReactNode;
  disabled?: boolean;
  buttonRef?: Ref<HTMLButtonElement>;
  type?: "button" | "submit";
  "aria-expanded"?: boolean;
  "aria-controls"?: string;
}) {
  return (
    <button
      className="icon-button"
      type={type}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      ref={buttonRef}
      {...rest}
    >
      {children}
      <span className="tooltip" role="tooltip">
        {label}
      </span>
    </button>
  );
}
