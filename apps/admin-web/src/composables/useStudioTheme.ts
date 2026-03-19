import { watch } from "vue";
import { createStorage } from "@vuetify/v0/storage";
import { createTheme } from "@vuetify/v0/theme";

export type StudioThemeMode = "studioLight" | "studioDark";

function resolveDefaultMode(): StudioThemeMode {
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "studioDark";
  }

  return "studioLight";
}

const storage = createStorage({
  prefix: "artificer:",
});

const storedMode = storage.get<StudioThemeMode>("admin-theme", resolveDefaultMode());

const theme = createTheme({
  default: storedMode.value,
  themes: {
    studioLight: {
      dark: false,
      colors: {
        primary: "#245a7d",
        secondary: "#c67b42",
        accent: "#2b8c7f",
        background: "#f6f2ea",
        surface: "#fffdfa",
      },
    },
    studioDark: {
      dark: true,
      colors: {
        primary: "#82cafc",
        secondary: "#f1aa6b",
        accent: "#7fe0c9",
        background: "#10141c",
        surface: "#171d28",
      },
    },
  },
});

if (storedMode.value && theme.selectedId.value !== storedMode.value) {
  theme.select(storedMode.value);
}

watch(
  theme.selectedId,
  (value) => {
    if (value === "studioLight" || value === "studioDark") {
      storedMode.value = value;
    }
  },
  { immediate: true },
);

export function useStudioTheme() {
  function setMode(nextMode: StudioThemeMode): void {
    theme.select(nextMode);
  }

  function toggle(): void {
    theme.cycle(["studioLight", "studioDark"]);
  }

  return {
    isDark: theme.isDark,
    mode: storedMode,
    setMode,
    theme,
    toggle,
  };
}
