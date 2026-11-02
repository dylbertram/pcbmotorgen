/** Camera survives editor remounts; pointer ownership never does. */
export class PreviewCamera {
  zoom = $state(1);
  panX = $state(0);
  panY = $state(0);
}
