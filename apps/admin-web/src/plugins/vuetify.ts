import "@mdi/font/css/materialdesignicons.css";
import "vuetify/styles";
import { createVuetify } from "vuetify";
import * as directives from "vuetify/directives";
import * as components from "vuetify/components";
import { aliases, mdi } from "vuetify/iconsets/mdi";
import { artificerThemes } from "../theme/artificerTheme";

export const vuetify = createVuetify({
  components,
  directives,
  icons: {
    defaultSet: "mdi",
    aliases,
    sets: {
      mdi,
    },
  },
  theme: {
    defaultTheme: "artificerDark",
    themes: artificerThemes,
  },
  defaults: {
    VCard: {
      elevation: 0,
      rounded: "lg",
    },
    VBtn: {
      density: "compact",
      rounded: "lg",
    },
    VChip: {
      density: "compact",
      rounded: "sm",
    },
    VTextField: {
      density: "compact",
      rounded: "sm",
      variant: "outlined",
    },
    VTextarea: {
      density: "compact",
      rounded: "sm",
      variant: "outlined",
    },
    VSelect: {
      density: "compact",
      rounded: "sm",
      variant: "outlined",
    },
    VCombobox: {
      density: "compact",
      rounded: "sm",
      variant: "outlined",
    },
    VAutocomplete: {
      density: "compact",
      rounded: "sm",
      variant: "outlined",
    },
    VSwitch: {
      density: "compact",
    },
    VTabs: {
      density: "compact",
    },
    VTab: {
      density: "compact",
    },
    VListItem: {
      density: "compact",
    },
    VPagination: {
      density: "compact",
    },
    VTable: {
      density: "compact",
    },
    VBtnGroup: {
      density: "compact",
    },
    VChipGroup: {
      density: "compact",
    },
    VList: {
      density: "compact",
    },
  },
});
