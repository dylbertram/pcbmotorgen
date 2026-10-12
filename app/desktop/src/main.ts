import "./app.css";
import { mount } from "svelte";
import App from "./App.svelte";
import { initializeAppearance } from "./lib/preferences";

const disposeAppearance = initializeAppearance();
if (import.meta.hot) import.meta.hot.dispose(disposeAppearance);
const app = mount(App, { target: document.getElementById("app")! });
export default app;
