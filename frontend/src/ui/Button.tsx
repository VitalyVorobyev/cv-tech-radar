// Minimal button — no shadows, 2px radius cap, hairline border.
// Variant "primary" uses accent color; "ghost" is text-only with underline.

import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
  size?: "sm" | "md";
}

export function Button({
  variant = "primary",
  size = "md",
  children,
  style,
  ...rest
}: ButtonProps) {
  const base: React.CSSProperties = {
    fontFamily: "var(--font-sans)",
    fontWeight: 500,
    borderRadius: "var(--radius-sm)",
    cursor: rest.disabled ? "default" : "pointer",
    transition: `opacity var(--duration-focus)`,
    border: "none",
    background: "transparent",
    padding: size === "sm" ? "0.25rem 0.75rem" : "0.375rem 1rem",
    fontSize: size === "sm" ? "var(--text-small)" : "var(--text-body)",
    lineHeight: 1.5,
    opacity: rest.disabled ? 0.45 : 1,
  };

  if (variant === "primary") {
    Object.assign(base, {
      background: "var(--color-ink)",
      color: "var(--color-paper)",
      border: "1px solid var(--color-ink)",
    });
  } else {
    Object.assign(base, {
      color: "var(--color-ink)",
      textDecoration: "underline",
      textUnderlineOffset: "2px",
      padding: 0,
    });
  }

  return (
    <button style={{ ...base, ...style }} {...rest}>
      {children}
    </button>
  );
}
