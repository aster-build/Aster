import type { SVGProps } from "react";

/*
 * Original icons drawn in the style of SF Symbols (rounded caps and joins,
 * medium weight, 90° arrowheads) on a 24px grid. SF Symbols themselves are
 * licensed only for Apple-platform apps, so they are not used on the web.
 */

type IconProps = Omit<SVGProps<SVGSVGElement>, "children"> & { size?: number; weight?: number };

function Icon({ size = 16, weight = 2, className, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={weight}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className ?? ""}`}
      {...rest}
    >
      {children}
    </svg>
  );
}

/** arrow.down */
export const ArrowDown = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4.5v15M5.75 13.25 12 19.5l6.25-6.25" />
  </Icon>
);

/** arrow.up */
export const ArrowUp = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 19.5v-15M5.75 10.75 12 4.5l6.25 6.25" />
  </Icon>
);

/** arrow.right */
export const ArrowRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 12h15M13.25 5.75 19.5 12l-6.25 6.25" />
  </Icon>
);

/** arrow.up.right */
export const ArrowUpRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 17 17 7M8.5 7H17v8.5" />
  </Icon>
);

/** arrow.down.to.line */
export const ArrowDownToLine = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5v12M6.75 10.25 12 15.5l5.25-5.25M5 20.5h14" />
  </Icon>
);

/** chevron.right */
export const ChevronRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="m9 5.5 6.5 6.5L9 18.5" />
  </Icon>
);

/** chevron.down */
export const ChevronDown = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5.5 9 12 15.5 18.5 9" />
  </Icon>
);

/** xmark */
export const XMark = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);

/** hexagon (a ring, for compound inputs) */
export const Hexagon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.25 19.6 7.6v8.8L12 20.75 4.4 16.4V7.6Z" />
    <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
  </Icon>
);

/** flask (experimental context) */
export const Flask = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 3.5h6M10.25 3.5v5.75L5.4 17.6a1.9 1.9 0 0 0 1.65 2.9h9.9a1.9 1.9 0 0 0 1.65-2.9l-4.85-8.35V3.5" />
    <path d="M7.6 14.5h8.8" />
  </Icon>
);

/** doc.text (research outputs) */
export const DocText = (p: IconProps) => (
  <Icon {...p}>
    <path d="M13.5 3.5H7.25A1.75 1.75 0 0 0 5.5 5.25v13.5c0 .97.78 1.75 1.75 1.75h9.5c.97 0 1.75-.78 1.75-1.75V8.5Z" />
    <path d="M13.5 3.5v5h5M9 13h6M9 16.5h4" />
  </Icon>
);
