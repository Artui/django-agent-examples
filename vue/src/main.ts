import { createApp, defineComponent } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./styles.css";

/**
 * The three routes exist so the agent's `navigate_to_route` has somewhere to go
 * and so the URL is the source of truth for which view is showing. They render
 * nothing themselves: `App` owns the board state and picks the view from the
 * current path, which keeps the state in one place without a store.
 */
const Blank = defineComponent({ render: () => null });

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/week" },
    { path: "/week", component: Blank },
    { path: "/day", component: Blank },
    { path: "/agenda", component: Blank },
  ],
});

createApp(App).use(router).mount("#app");
