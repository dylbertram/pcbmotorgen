import { expect, it } from "vitest";
import { OrthographicCamera } from "three";
import { TERMINAL_MARKER_SIZE_PX, terminalMarkerPickRadius, terminalMarkerTexture } from "./terminalMarkers";

it("keeps marker picking matched to its screen size across zoom and viewport changes",()=>{
  for(const height of [300,800]) for(const zoom of [1,100,10000]){
    const camera=new OrthographicCamera(-300,300,height/2,-height/2);
    camera.zoom=zoom;
    expect(terminalMarkerPickRadius(camera,height)*zoom).toBeCloseTo(TERMINAL_MARKER_SIZE_PX/2,12);
  }
});

it("uses a circular annotation instead of a physical sphere or square",()=>{
  const texture=terminalMarkerTexture(),{data,width,height}=texture.image;
  expect(data![3]).toBe(0);
  expect(data![(Math.floor(height/2)*width+Math.floor(width/2))*4+3]).toBe(255);
  texture.dispose();
});
