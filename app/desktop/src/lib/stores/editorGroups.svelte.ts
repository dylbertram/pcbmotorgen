import { DocumentView, type DocumentSession } from "./documentSession.svelte";

export type EditorSide = "left" | "right";
export class EditorGroups {
  left = $state<number[]>([]);
  right = $state<number[]>([]);
  leftActive = $state<number | null>(null);
  rightActive = $state<number | null>(null);
  focusedGroup = $state<EditorSide>("left");
  leftPercent = $state(50);
  splitOpen = $derived(this.right.length > 0);
  private known = new Set<number>();
  private views = new Map<string, DocumentView>();

  tabs(side: EditorSide): number[] { return this[side]; }
  selected(side: EditorSide): number | null { return side === "left" ? this.leftActive : this.rightActive; }
  select(side: EditorSide, id: number): void {
    if (!this[side].includes(id)) return;
    this.focusedGroup = side;
    if (side === "left") this.leftActive = id;
    else this.rightActive = id;
  }
  sync(documents: DocumentSession[], activeId: number | null): void {
    const ids = new Set(documents.map(d => d.id));
    this.left = this.left.filter(id => ids.has(id));
    this.right = this.right.filter(id => ids.has(id));
    for (const id of ids) if (!this.known.has(id)) this[this.focusedGroup] = [...this[this.focusedGroup], id];
    for (const id of this.known) if (!ids.has(id)) { this.views.delete(`left:${id}`); this.views.delete(`right:${id}`); }
    this.known = ids;
    this.normalize();
    if (activeId !== null) {
      const side = this[this.focusedGroup].includes(activeId) ? this.focusedGroup : this.left.includes(activeId) ? "left" : "right";
      this.select(side, activeId);
    }
  }
  splitRight(id: number): void {
    if (!this.known.has(id)) return;
    if (!this.right.includes(id)) this.right = [...this.right, id];
    this.select("right", id);
  }
  move(id: number, from: EditorSide, to: EditorSide): void {
    if (!this[from].includes(id) || from === to) return;
    if (!this[to].includes(id)) {
      this[to] = [...this[to], id];
      const view = this.views.get(`${from}:${id}`);
      if (view) this.views.set(`${to}:${id}`, view);
    }
    this.views.delete(`${from}:${id}`);
    this[from] = this[from].filter(value => value !== id);
    this.select(to, id);
    this.normalize();
  }
  removeView(id: number, side: EditorSide): void {
    this[side] = this[side].filter(value => value !== id);
    this.views.delete(`${side}:${id}`);
    this.normalize();
  }
  view(document: DocumentSession, side: EditorSide): DocumentView {
    const key = `${side}:${document.id}`;
    let view = this.views.get(key);
    if (!view) { view = side === "left" ? document : new DocumentView(); this.views.set(key, view); }
    return view;
  }
  resize(value: number): void { if (Number.isFinite(value)) this.leftPercent = Math.min(75, Math.max(25, value)); }
  private normalize(): void {
    if (!this.left.length && this.right.length) {
      for (const id of this.right) {
        const view = this.views.get(`right:${id}`);
        if (view) { this.views.set(`left:${id}`, view); this.views.delete(`right:${id}`); }
      }
      this.left = this.right;
      this.leftActive = this.rightActive;
      this.right = [];
      this.rightActive = null;
      this.focusedGroup = "left";
    }
    if (!this.left.includes(this.leftActive!)) this.leftActive = this.left[0] ?? null;
    if (!this.right.includes(this.rightActive!)) this.rightActive = this.right[0] ?? null;
    if (!this.right.length) this.focusedGroup = "left";
  }
}
