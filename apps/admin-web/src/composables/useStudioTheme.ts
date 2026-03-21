import { computed, watch } from "vue";
import { createStorage } from "@vuetify/v0/storage";
import { createTheme } from "@vuetify/v0/theme";
import { artificerThemes, normalizeThemeMode, type ArtificerThemeMode } from "../theme/artificerTheme";

export type StudioThemeMode = ArtificerThemeMode;
type PersistedThemeMode = StudioThemeMode | "studioLight" | "studioDark";

function resolveDefaultMode(): StudioThemeMode {
  return "artificerDark";
}

const storage = createStorage({
  prefix: "artificer:",
});

const storedMode = storage.get<PersistedThemeMode>("admin-theme", resolveDefaultMode());
const mode = computed<StudioThemeMode>({
  get: () => normalizeThemeMode(storedMode.value),
  set: (value) => {
    storedMode.value = value;
    theme.select(value);
  },
});

const theme = createTheme({
  default: mode.value,
  themes: artificerThemes,
});

if (storedMode.value !== mode.value) {
  storedMode.value = mode.value;
}

if (theme.selectedId.value !== mode.value) {
  theme.select(mode.value);
}

watch(
  theme.selectedId,
  (value) => {
    const normalized = normalizeThemeMode(value);
    if (theme.selectedId.value !== normalized) {
      theme.select(normalized);
    }
    if (storedMode.value !== normalized) {
      storedMode.value = normalized;
    }
  },
  { immediate: true },
);

export function useStudioTheme() {
  function setMode(nextMode: StudioThemeMode): void {
    mode.value = nextMode;
  }

  function toggle(): void {
    theme.cycle(["artificerDark", "artificerLight"]);
  }

  return {
    isDark: theme.isDark,
    mode,
    setMode,
    theme,
    toggle,
  };
}
