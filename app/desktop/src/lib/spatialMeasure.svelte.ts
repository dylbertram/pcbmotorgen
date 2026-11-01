export interface PhysicalPoint { x: number; y: number; z: number }

export class SpatialMeasure {
  mode = $state(false);
  p1 = $state<PhysicalPoint | null>(null);
  p2 = $state<PhysicalPoint | null>(null);
  cursor = $state<PhysicalPoint | null>(null);
  distanceMm = $derived.by(() => {
    const end = this.p2 ?? this.cursor;
    return this.p1 && end ? Math.hypot(end.x - this.p1.x, end.y - this.p1.y, end.z - this.p1.z) : null;
  });
  clear = () => { this.p1 = null; this.p2 = null; this.cursor = null; };
  toggleMode = () => { this.mode = !this.mode; if (!this.mode) this.clear(); };
  pick(point: PhysicalPoint): void {
    if (!this.mode) return;
    if (this.p2) this.clear();
    else if (this.p1) { this.p2 = point; this.cursor = null; }
    else { this.p1 = point; this.cursor = null; }
  }
}
