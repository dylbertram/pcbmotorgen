import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Vitest unit-test configuration.
//
// Co-located test files follow the `*.test.ts` convention and live next to
// the module they exercise (e.g. `lib/geometry/isometric.ts` and its test).
// Tests run in the plain node environment; the Svelte plugin is included so
// future component tests can import `.svelte` files if needed.
export default defineConfig({
  plugins: [svelte()],
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
});
