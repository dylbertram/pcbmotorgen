import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gotoDesignApp, openCoilPreview } from "./helpers";

for (const layers of [2, 4, 6, 8]) {
  test(`native ${layers}-layer braid renders its complete via barrels`, async ({ page }, info) => {
    const directory = process.env.PCB_MOTOR_TERMINAL_FIXTURES;
    test.skip(!directory, "Requires exported native braid payloads.");
    const coils = readFileSync(join(directory!, `generated-${layers}-preview.json`), "utf8");
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.stack ?? error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, route => route.fulfill({
      contentType: "application/javascript",
      body: `export * from '/src/lib/ipc/physics.ts?original'; export async function generateCoils() { return ${coils}; }`,
    }));
    try {
      await gotoDesignApp(page);
      await page.getByRole("button", { name: "Copper layer count", exact: true }).click();
      await page.getByRole("option", { name: String(layers), exact: true }).click();
      await openCoilPreview(page);
      await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
      const viewer = page.getByTestId("coil-iso");
      await expect(viewer).toHaveAttribute("data-layers", String(layers));
      await expect(viewer.locator("canvas")).toBeVisible();
      await expect(viewer.getByRole("status").filter({ hasText: "3D rendering is unavailable" })).toHaveCount(0);
      await expect(viewer).toHaveAttribute("data-vias", /[1-9]/);
      const viaCount=(await viewer.getAttribute("data-vias"))!;
      for(const [label,id] of [["Top-down","top"],["Front","front"],["Left","left"],["3D fields and heat","iso"]]){
        await page.getByRole("button",{name:label,exact:true}).click();
        const shared=page.getByTestId(`coil-${id}`);
        await expect(shared).toHaveAttribute("data-renderer","shared-three");
        await expect(shared).toHaveAttribute("data-layers",String(layers));
        await expect(shared).toHaveAttribute("data-vias",viaCount);
        await expect(shared.locator("canvas")).toBeVisible();
      }
      if (layers > 2) {
        // Through-vias still cross an inner layer when both outer layers are hidden.
        const expectedVias = await page.evaluate(async ({ coils, layers }) => {
          const { generatedTerminalGeometry } = await import(/* @vite-ignore */ "/src/lib/generatedTerminalGeometry.ts");
          const geometry = generatedTerminalGeometry(JSON.parse(coils), layers, 1.6, .2, 2);
          return geometry.routing.vias.filter(via => Math.min(via.from_layer, via.to_layer) <= 1 && Math.max(via.from_layer, via.to_layer) >= 1).length;
        }, { coils, layers });
        await page.getByRole("button", { name: "Layers", exact: true }).click();
        const display = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
        await display.getByRole("radio", { name: "Layers", exact: true }).check();
        for (let index = 0; index < layers; index++) {
          if (index !== 1) await display.getByRole("checkbox", { name: `Show layer ${index}`, exact: true }).uncheck();
        }
        await expect(viewer).toHaveAttribute("data-layers", "1");
        await expect(viewer).toHaveAttribute("data-vias", String(expectedVias));
      }
      await page.screenshot({ path: info.outputPath(`native-${layers}-layer-3d.png`) });
      expect(errors).toEqual([]);
    } finally {
      await info.attach("browser-errors", { body: JSON.stringify(errors, null, 2), contentType: "application/json" });
    }
  });
}
