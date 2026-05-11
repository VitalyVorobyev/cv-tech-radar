// Pure typographic ring renderer.
// No background, no border, no padding — ring identity is expressed through
// font weight, casing, style, and decoration only.
// Accent color (amber) is reserved for Use and Prototype.

import type { Ring } from "../lib/api";

interface RingLabelProps {
  ring: Ring;
  className?: string;
}

export function RingLabel({ ring, className = "" }: RingLabelProps) {
  const base = `font-sans ${className}`;

  switch (ring) {
    case "Use":
      // Uppercase bold, accent color, wide tracking
      return (
        <span
          className={base}
          style={{
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "var(--tracking-caps)",
            color: "var(--color-accent)",
          }}
        >
          use
        </span>
      );

    case "Prototype":
      // Caps-first, medium weight, accent color, slight tracking
      return (
        <span
          className={base}
          style={{
            fontWeight: 500,
            fontVariant: "small-caps",
            letterSpacing: "var(--tracking-caps)",
            color: "var(--color-accent)",
          }}
        >
          Prototype
        </span>
      );

    case "Evaluate":
      // Italic regular, foreground color
      return (
        <span
          className={base}
          style={{
            fontStyle: "italic",
            fontWeight: 400,
          }}
        >
          Evaluate
        </span>
      );

    case "Watch":
      // Lowercase muted regular
      return (
        <span
          className={`${base} text-muted`}
          style={{
            fontWeight: 400,
            textTransform: "lowercase",
          }}
        >
          watch
        </span>
      );

    case "Ignore":
      // Muted with strikethrough
      return (
        <span
          className={`${base} text-muted`}
          style={{
            fontWeight: 400,
            textDecoration: "line-through",
          }}
        >
          ignore
        </span>
      );
  }
}
