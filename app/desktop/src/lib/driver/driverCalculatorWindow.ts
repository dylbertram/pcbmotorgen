import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isTauriAvailable } from "../ipc/core";
import { errorMessage } from "../utils/errorMessage";
import type { DriverCalculatorSnapshot } from "./driverCalculator";

let popup: Window | null = null;
const SEED = "pcbmotorgen:driver-calculator-seed";
export async function openDriverCalculator(snapshot: DriverCalculatorSnapshot | null): Promise<void> {
  if (isTauriAvailable()) { await invoke("open_driver_calculator", { snapshot }); return; }
  if (popup && !popup.closed) { popup.focus(); return; }
  sessionStorage.setItem(SEED, JSON.stringify(snapshot));
  popup = window.open("/?tool=driver-calculator", "pcbmotorgen-driver-calculator", "popup,width=1100,height=800");
  if (!popup) throw new Error("The calculator window was blocked. Allow pop-up windows for this app.");
}
export async function calculatorSeed(): Promise<DriverCalculatorSnapshot | null> {
  if (isTauriAvailable()) return invoke("driver_calculator_seed");
  const raw = sessionStorage.getItem(SEED);
  sessionStorage.removeItem(SEED);
  return raw ? JSON.parse(raw) : null;
}
export async function requestDriverImport(requestId: string): Promise<void> {
  if (isTauriAvailable()) { await invoke("request_driver_calculator_import", { requestId }); return; }
  if (!window.opener || window.opener.closed) throw new Error("The motor window is closed. Calculator inputs are still editable.");
  window.opener.postMessage({ type: "driver-calculator:import", requestId }, window.location.origin);
}
export async function bindDriverImports(getSnapshot: () => Promise<DriverCalculatorSnapshot | null> | null): Promise<() => void> {
  const result = async () => {
    try {
      const snapshot = await getSnapshot();
      return { snapshot, error: snapshot ? null : "No current motor winding analysis is available. Select a motor or enter winding values manually." };
    } catch (e) { return { snapshot: null, error: `No current motor winding analysis is available. ${errorMessage(e)}` }; }
  };
  if (isTauriAvailable()) return listen<string>("driver-calculator:import", async event => { await invoke("provide_driver_calculator_import", { result: { requestId: event.payload, ...await result() } }); });
  const handler = async (event: MessageEvent) => {
    if (event.origin !== window.location.origin || event.source !== popup || event.data?.type !== "driver-calculator:import") return;
    const target = popup;
    const requestId = event.data.requestId;
    if (typeof requestId !== "string" || requestId.length > 128) return;
    target?.postMessage({ type: "driver-calculator:result", requestId, ...await result() }, window.location.origin);
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}
export async function listenDriverImport(handler: (result: { requestId: string; snapshot: DriverCalculatorSnapshot | null; error: string | null }) => void): Promise<() => void> {
  if (isTauriAvailable()) return listen<{ requestId: string; snapshot: DriverCalculatorSnapshot | null; error: string | null }>("driver-calculator:result", event => handler(event.payload));
  const listener = (event: MessageEvent) => {
    if (event.origin === window.location.origin && event.source === window.opener && event.data?.type === "driver-calculator:result") handler(event.data);
  };
  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}
