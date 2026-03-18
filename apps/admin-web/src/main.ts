import { createApp } from "vue";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";
import App from "./App.vue";
import { router } from "./router";
import { vuetify } from "./plugins/vuetify";
import "./styles/main.css";

const app = createApp(App);

app.use(vuetify);
app.use(router);

app.mount("#app");
