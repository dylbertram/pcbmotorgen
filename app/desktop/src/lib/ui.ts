/**
 * Shared UI enums/constants for the app shell tabs.
 * Extracted from App.svelte so the layout components and the shell agree on
 * the same vocabulary.
 */

/** Top-level workflow tabs. Export lives in the native File menu; the sensor
 *  is a design type, not a tab. */
export type TabId = "design" | "simulate";
export type DesignType = "motor" | "sensor";

/** Tab order + labels — matches the old inline `tabs` array in App.svelte. */
export const TABS: { id: TabId; label: string }[] = [
  { id: "design", label: "Design" },
  { id: "simulate", label: "Simulate" },
];
