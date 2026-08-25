import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./styles.css";

const app = createApp(App);

app.config.errorHandler = (error, _instance, info) => {
  console.error("[scenara] unhandled application error:", error, "info:", info);
};

app.use(router).mount("#app");
