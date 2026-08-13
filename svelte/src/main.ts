import { mount } from "svelte";
import App from "./App.svelte";
import "./styles.css";

const target = document.getElementById("app");
if (target === null) {
  throw new Error("index.html is missing #app");
}

mount(App, { target });
