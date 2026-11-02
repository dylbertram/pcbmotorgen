import { DataTexture, LinearFilter, type OrthographicCamera } from "three";

export const TERMINAL_MARKER_SIZE_PX = 8;

export function terminalMarkerPickRadius(camera: Pick<OrthographicCamera, "top" | "bottom" | "zoom">, heightPx: number): number {
  return TERMINAL_MARKER_SIZE_PX / 2 * (camera.top - camera.bottom) / (heightPx * camera.zoom);
}

/** White circle with a soft alpha edge, tinted by PointsMaterial. No DOM canvas. */
export function terminalMarkerTexture(): DataTexture {
  const size = 32, data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const i = (y * size + x) * 4;
    data[i] = data[i + 1] = data[i + 2] = 255;
    data[i + 3] = Math.round(255 * Math.min(1, Math.max(0, size / 2 - Math.hypot(x + .5 - size / 2, y + .5 - size / 2))));
  }
  const texture = new DataTexture(data, size, size);
  texture.magFilter = texture.minFilter = LinearFilter;
  texture.needsUpdate = true;
  return texture;
}
