import { mount, unmount } from "svelte";
import NativeVisualizationScene from "./NativeVisualizationScene.svelte";
import { generatedTerminalGeometry } from "../../src/lib/generatedTerminalGeometry";
import { validateVisualization } from "../../src/lib/simulationVisualizationController";

export function renderFrozenNativeReport(value: any) {
  validateVisualization(value.report, value.request);
  const c = value.config;
  const geometry = value.cad_geometry ?? generatedTerminalGeometry(value.coils, c.num_layers, c.pcb_thickness_m * 1000, c.trace_width_m * 1000);
  const component = mount(NativeVisualizationScene, { target: document.body, props: { geometry, field: value.report.field, loss: value.report.heat } });
  return () => unmount(component);
}

export function renderFrozenNativeWindingReport(value: any, winding: any) {
  if (winding.status !== "sampled-qualified-finite-copper-winding-field-only" || winding.field.method !== "qualified-finite-copper-winding-xyz"
    || winding.field.magnets.length || winding.source_elements < 1 || "pm_array_force_n" in winding) throw new Error("Not a native finite-copper winding-field report");
  const c=value.config;
  const geometry=value.cad_geometry ?? generatedTerminalGeometry(value.coils,c.num_layers,c.pcb_thickness_m*1000,c.trace_width_m*1000);
  const component=mount(NativeVisualizationScene,{target:document.body,props:{geometry,field:winding.field}});
  return () => unmount(component);
}
