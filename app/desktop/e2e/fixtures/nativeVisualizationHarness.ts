import { mount, unmount } from "svelte";
import NativeVisualizationScene from "./NativeVisualizationScene.svelte";
import { generatedTerminalGeometry } from "../../src/lib/generatedTerminalGeometry";
import { validateVisualization } from "../../src/lib/simulationVisualizationController";

export function renderFrozenNativeReport(value: any) {
  validateVisualization(value.report, value.request);
  const c = value.config;
  const geometry = value.cad_geometry ?? generatedTerminalGeometry(value.coils, c.num_layers, c.pcb_thickness_m * 1000, c.trace_width_m * 1000);
  const component = mount(NativeVisualizationScene, { target: document.body, props: { geometry, report: value.report } });
  return () => unmount(component);
}
