// Platform-neutral design tokens. DOM and native views consume the same meanings.
export const colors = {
  background: "#0b121b",
  panel: "#131d29",
  raised: "#1b2a3c",
  border: "#29394b",
  text: "#edf3fa",
  muted: "#92a4b8",
  positive: "#39d6bd",
  negative: "#f1867d",
  accent: "#8ab8ef",
  warning: "#eac483",
};
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 };
export const radius = { panel: 14, control: 9 };
export const touchTarget = 44;
export const navigation = [
  "Home",
  "Research",
  "Portfolio",
  "Activity",
  "More",
] as const;
export type Page = (typeof navigation)[number];
