import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

/**
 * In-app plugin authoring guide + routing-pattern select suite (kata bprp,
 * migrated to Bits UI Select/Dialog primitives in kata 1hx7).
 *
 * The routing-pattern "dropdown" is a Bits UI Select (trigger button +
 * listbox, not a native <select>): the mock catalog offers exactly one
 * pattern ("Infinity Braid (pcbBraid)"), rendered above a visual separator
 * and the "+ Load new generator…" sentinel ACTION — picking the sentinel
 * opens the upload dialog and must NOT change the selection.
 *
 * The guide modal must be reachable from the generator upload panel
 * ("How to write a plugin?" entry point) and its content must come from the
 * docs BUNDLED AT BUILD TIME from crates/pcbmotorgen-routing/docs (via Vite
 * `?raw` imports) — the assertions below check for verbatim doc headings so
 * a forked/empty placeholder body would fail.
 *
 * Stacked-modal discipline (kata xy31 scroll-lock precedent, now via Bits
 * UI dialog layers): the guide opens ABOVE the upload dialog; Escape closes
 * ONLY the topmost dialog while the page scroll lock stays engaged
 * (refcounted custom helpers), and the second Escape closes the upload
 * dialog and releases the lock.
 */

const PATTERN_TRIGGER = "#routing-pattern";
const MOCK_PATTERN_LABEL = "Infinity Braid (pcbBraid)";
const SENTINEL_LABEL = "+ Load new generator…";
const UPLOAD_DIALOG = "[role='dialog'][aria-label='Load new generator']";
const HELP_BUTTON = "button[aria-haspopup='dialog']:has-text('How to write a plugin?')";
const GUIDE_DIALOG = "[role='dialog'][aria-label='How to write a routing plugin']";

test.describe("routing pattern select (Bits UI) @interaction @desktop", () => {
  test("lists the catalog above a separator, and the sentinel opens the upload dialog without changing the selection", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    const trigger = page.locator(PATTERN_TRIGGER);
    await expect(trigger).toContainText(MOCK_PATTERN_LABEL);

    await trigger.click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    await expect(
      listbox.getByRole("option", { name: MOCK_PATTERN_LABEL }),
    ).toBeVisible();
    // The divider is the ui/Separator design-system wrapper (kata tn66):
    // decorative, so it renders role="none" + aria-hidden instead of
    // role="separator" — purely visual, neither focusable nor selectable.
    await expect(
      listbox.locator("[role='none'][data-orientation='horizontal']"),
    ).toHaveCount(1);
    await expect(
      listbox.getByRole("option", { name: SENTINEL_LABEL }),
    ).toBeVisible();

    // The sentinel is an action, not a value: the upload dialog opens and
    // the trigger still shows the active pattern.
    await listbox.getByRole("option", { name: SENTINEL_LABEL }).click();
    await expect(page.locator(UPLOAD_DIALOG)).toBeVisible();
    await expect(trigger).toContainText(MOCK_PATTERN_LABEL);

    // Escape closes the upload dialog and releases the scroll lock.
    await page.keyboard.press("Escape");
    await expect(page.locator(UPLOAD_DIALOG)).toBeHidden();
    expect(
      await page.evaluate(() => document.documentElement.style.overflow),
    ).toBe("");
  });

  test("choosing a real pattern keeps the selection and closes the dropdown", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    const trigger = page.locator(PATTERN_TRIGGER);
    await trigger.click();
    await page
      .getByRole("option", { name: MOCK_PATTERN_LABEL })
      .click();

    await expect(trigger).toContainText(MOCK_PATTERN_LABEL);
    await expect(page.getByRole("listbox")).toHaveCount(0);

    // The pattern-declared routing params section still renders below.
    await expect(page.locator("#routing-parameters-heading")).toBeVisible();
  });
});

test.describe("plugin authoring guide @interaction @desktop", () => {
  test("opens from the upload panel, renders the bundled crate docs, and closes independently", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    // Open the "Load new generator" modal via the pattern-select sentinel.
    await page.locator(PATTERN_TRIGGER).click();
    await page
      .getByRole("option", { name: SENTINEL_LABEL })
      .click();
    await expect(page.locator(UPLOAD_DIALOG)).toBeVisible();

    // The entry point inside the upload panel opens the stacked guide.
    await page.locator(HELP_BUTTON).click();
    const guide = page.locator(GUIDE_DIALOG);
    await expect(guide).toBeVisible();

    // Verbatim headings from routing-pattern-authoring.md — proves the body
    // is the bundled doc, not a stub (and that no runtime fetch is needed).
    await expect(guide).toContainText("The contract in one paragraph");
    await expect(guide).toContainText("Authoring a Rust cdylib plugin");

    // Landed features must be documented (we8r layer ranges + multiple_of,
    // hzs2 phase bands, htcq IO elements) — no "coming soon" placeholders.
    await expect(guide).toContainText("layers_multiple_of");
    await expect(guide).toContainText("phase_bands");
    await expect(guide).toContainText("io_pads");

    // The worked example tab bundles the reference runner verbatim.
    await page.getByRole("tab", { name: "Worked example" }).click();
    await expect(guide).toContainText('"id": "example-runner"');

    // Escape closes ONLY the guide; the upload dialog stays open and the
    // refcounted scroll lock stays engaged while it does.
    await page.keyboard.press("Escape");
    await expect(guide).toBeHidden();
    await expect(page.locator(UPLOAD_DIALOG)).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.style.overflow),
    ).toBe("hidden");

    // Second Escape closes the upload dialog and releases the lock.
    await page.keyboard.press("Escape");
    await expect(page.locator(UPLOAD_DIALOG)).toBeHidden();
    expect(
      await page.evaluate(() => document.documentElement.style.overflow),
    ).toBe("");
  });
});
