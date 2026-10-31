import { mount, unmount } from "svelte";
import PhysicalCopperDetail from "./PhysicalCopperDetail.svelte";

/** Deterministic geometry rendered by the production viewer and camera. */
export function renderCopperDetail() {
  const component=mount(PhysicalCopperDetail,{target:document.body});
  return ()=>unmount(component);
}
