export type ArtificerThemeMode = "artificerDark" | "artificerLight";

export const artificerDarkTheme = {
  dark: true,
  colors: {
    background: "#0A0E12",
    surface: "#111827",
    "surface-bright": "#1F2933",
    "surface-light": "#1A222C",
    "surface-variant": "#243040",
    primary: "#22D3EE",
    "primary-darken-1": "#06B6D4",
    secondary: "#8B95A7",
    "secondary-darken-1": "#4B5563",
    accent: "#67E8F9",
    info: "#38BDF8",
    success: "#22C55E",
    warning: "#F59E0B",
    error: "#EF4444",
    "on-background": "#F3F4F6",
    "on-surface": "#F3F4F6",
    "on-surface-variant": "#A3ADBD",
    "on-primary": "#0A0E12",
    "on-secondary": "#F3F4F6",
    "on-success": "#052E1A",
    "on-warning": "#3A2A05",
    "on-error": "#3B0A0A",
    outline: "#2A3442",
    "outline-variant": "#364152",
    scrim: "#000000",
    "inverse-surface": "#F8FAFC",
    "inverse-on-surface": "#0F172A",
    "inverse-primary": "#0891B2",
  },
};

export const artificerLightTheme = {
  dark: false,
  colors: {
    background: "#F8FAFC",
    surface: "#FFFFFF",
    "surface-bright": "#F1F5F9",
    "surface-light": "#E5E7EB",
    "surface-variant": "#E2E8F0",
    primary: "#0891B2",
    "primary-darken-1": "#0E7490",
    secondary: "#64748B",
    "secondary-darken-1": "#334155",
    accent: "#22D3EE",
    info: "#0284C7",
    success: "#16A34A",
    warning: "#D97706",
    error: "#DC2626",
    "on-background": "#0F172A",
    "on-surface": "#0F172A",
    "on-surface-variant": "#334155",
    "on-primary": "#F8FAFC",
    "on-secondary": "#F8FAFC",
    "on-success": "#DCFCE7",
    "on-warning": "#FFF7ED",
    "on-error": "#FEF2F2",
    outline: "#D1D5DB",
    "outline-variant": "#CBD5E1",
    scrim: "#000000",
    "inverse-surface": "#111827",
    "inverse-on-surface": "#F3F4F6",
    "inverse-primary": "#22D3EE",
  },
};

export const artificerThemes = {
  artificerDark: artificerDarkTheme,
  artificerLight: artificerLightTheme,
};

export function normalizeThemeMode(value: string | number | null | undefined): ArtificerThemeMode {
  if (value === "artificerLight" || value === "studioLight") {
    return "artificerLight";
  }

  return "artificerDark";
}
