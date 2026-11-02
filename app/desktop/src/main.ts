import "./app.css";
import { mount } from "svelte";
import App from "./App.svelte";
import DriverCalculator from "./DriverCalculator.svelte";
import { initializeAppearance } from "./lib/preferences";

const disposeAppearance = initializeAppearance();
if (import.meta.hot) import.meta.hot.dispose(disposeAppearance);
const component = new URLSearchParams(window.location.search).get("tool") === "driver-calculator" ? DriverCalculator : App;
const app = mount(component, { target: document.getElementById("app")! });
export default app;
