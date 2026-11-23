/**
 * Passpartout design tokens — single source of truth for all visual styling.
 * Change colours, fonts, spacing or radii here to rebrand the whole app.
 */

export const theme = {
  colors: {
    bg: "#F6F6F3",
    text: "#15181C",
    textMuted: "#5C6370",
    accent: "#1F6F66",
    accentLight: "#E8F5F2",
    amber: "#8A5A12",
    amberLight: "#FEF3E2",
    card: "#FFFFFF",
    border: "#E2E2DE",
    navBg: "#FFFFFF",
    demoBadge: "#8A5A12",
    demoBadgeBg: "#FEF3E2",
  },
  fonts: {
    body: "var(--font-inter)",
    heading: "var(--font-space-grotesk)",
  },
  radius: {
    card: "16px",
    button: "10px",
    badge: "8px",
    full: "9999px",
  },
  spacing: {
    page: "16px",
    cardPad: "20px",
    sectionGap: "24px",
  },
} as const;
