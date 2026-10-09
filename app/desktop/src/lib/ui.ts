/**
 * Shared UI enums/constants for the app shell (tabs, export targets).
 * Extracted from App.svelte so the layout components and the shell agree on
 * the same vocabulary.
 */

/** Top-level workflow tabs. */
export type TabId = "design" | "simulate" | "sensor" | "export";

/** Export panel target picker. */
export type ExportTarget = "kicad" | "dxf";

/** Tab order + labels — matches the old inline `tabs` array in App.svelte. */
export const TABS: { id: TabId; label: string }[] = [
  { id: "design", label: "Design" },
  { id: "simulate", label: "Simulate" },
  { id: "sensor", label: "Sensor" },
  { id: "export", label: "Export" },
];
