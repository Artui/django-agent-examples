import type { Routes } from "@angular/router";
import { App } from "./app";

/**
 * The three routes the agent may navigate to. They all render the same component:
 * the board's state lives in a service, and the view is chosen from the URL, which
 * keeps the state in one place.
 */
export const routes: Routes = [
  { path: "", redirectTo: "week", pathMatch: "full" },
  { path: "week", component: App },
  { path: "day", component: App },
  { path: "agenda", component: App },
];
