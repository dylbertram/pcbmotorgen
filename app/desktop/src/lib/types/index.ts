/**
 * pcbmotorgen — IPC contract types for the Svelte frontend.
 *
 * Barrel re-export of the per-domain type modules. All physical quantities
 * on the wire are SI (metres, Tesla, Amperes, Ohms, Watts, Newtons). The UI
 * store keeps human-readable mm values and converts at the invoke boundary.
 *
 * Consumers can keep importing from `../types` — this barrel resolves it.
 */

export * from "./coils";
export * from "./config";
export * from "./dxf";
export * from "./enums";
export * from "./kicad";
export * from "./magnets";
export * from "./physics";
export * from "./project";
export * from "./routing";
export * from "./sensor";
