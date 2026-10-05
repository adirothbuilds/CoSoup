// Shared palettes; native screens retain the dark default until a theme is chosen.
export const themes = {
  light: {
    background: "#f8f6f0",
    panel: "#fffefa",
    raised: "#f0eee5",
    border: "#deded2",
    text: "#293b35",
    muted: "#62736a",
    positive: "#267461",
    negative: "#a2493d",
    accent: "#326f5d",
    warning: "#91651e",
  },
  dark: {
    background: "#17211f",
    panel: "#202d29",
    raised: "#2b3933",
    border: "#3b4a41",
    text: "#f2eee3",
    muted: "#b2beb3",
    positive: "#83cbb3",
    negative: "#ec9b87",
    accent: "#a2cfb3",
    warning: "#e5bf7d",
  },
};
export const colors = themes.dark;
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
