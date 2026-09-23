import type { ReactNode } from "react";

/** MilpBook LM mark: an open evidence page with a citation spark. */
export function BrandMark({ className }: { readonly className?: string }): ReactNode {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="30" height="30" rx="7" fill="var(--surface-panel)" />
      <rect
        x="1.5"
        y="1.5"
        width="29"
        height="29"
        rx="6.5"
        fill="none"
        stroke="var(--border-default)"
      />
      <path
        d="M16 10.4 C13 8.9 9.4 8.8 5.5 10.4 V22 C9.4 20.4 13 20.5 16 22 Z"
        fill="var(--text-primary)"
      />
      <path
        d="M16 10.4 C19 8.9 22.6 8.8 26.5 10.4 V22 C22.6 20.4 19 20.5 16 22 Z"
        fill="var(--text-primary)"
      />
      <path
        d="M16 10.7 V21.7"
        stroke="var(--accent-primary)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M24.5 2.5 L25.4 4.5 L27.4 5.4 L25.4 6.3 L24.5 8.3 L23.6 6.3 L21.6 5.4 L23.6 4.5 Z"
        fill="var(--accent-primary)"
      />
    </svg>
  );
}
