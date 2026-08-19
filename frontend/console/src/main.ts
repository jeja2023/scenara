import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./styles.css";

const app = createApp(App);

app.config.errorHandler = (error, _instance, info) => {
  console.error("[scenara] unhandled application error", { info, error });
};

app.use(router).mount("#app");
