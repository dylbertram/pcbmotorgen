import { describe, expect, it } from "vitest";
import { EditorGroups } from "./editorGroups.svelte";
import { DocumentSession } from "./workspace.svelte";

describe("file editor groups", () => {
  it("splits one model into two independent views without duplicating the file", () => {
    const source = new DocumentSession("motor"), groups = new EditorGroups();
    groups.sync([source], source.id);
    groups.splitRight(source.id);
    expect(groups.left).toEqual([source.id]);
    expect(groups.right).toEqual([source.id]);
    expect(groups.view(source, "left")).not.toBe(groups.view(source, "right"));
    groups.view(source, "left").analysis.simulationView = "force";
    expect(groups.view(source, "right").analysis.simulationView).toBe("move");
    groups.removeView(source.id, "right");
    expect(groups.splitOpen).toBe(false);
    expect(groups.left).toEqual([source.id]);
  });
  it("moves tabs in both directions and collapses an empty group", () => {
    const a = new DocumentSession("motor"), b = new DocumentSession("sensor"), groups = new EditorGroups();
    groups.sync([a, b], b.id);
    groups.move(b.id, "left", "right");
    expect(groups.left).toEqual([a.id]);
    expect(groups.right).toEqual([b.id]);
    groups.move(b.id, "right", "left");
    expect(groups.left).toEqual([a.id, b.id]);
    expect(groups.right).toEqual([]);
    groups.splitRight(a.id);
    groups.sync([b], b.id);
    expect(groups.left).toEqual([b.id]);
    expect(groups.splitOpen).toBe(false);
  });
  it("does not resurrect closed views when focus or source data changes", () => {
    const a = new DocumentSession("motor"), b = new DocumentSession("motor"), groups = new EditorGroups();
    groups.sync([a, b], a.id);
    groups.move(a.id, "left", "right");
    groups.sync([a, b], a.id);
    expect(groups.left).toEqual([b.id]);
    expect(groups.right).toEqual([a.id]);
    groups.resize(NaN); expect(groups.leftPercent).toBe(50);
    groups.resize(1); expect(groups.leftPercent).toBe(25);
    groups.resize(100); expect(groups.leftPercent).toBe(75);
  });
});
