<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { BufferGeometry, RingGeometry, DoubleSide } from "three";
  import type { Vector3 } from "three";
  import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
  let { points, diameter, drill, zScale }: { points:Vector3[];diameter:number;drill:number;zScale:number } = $props();
  const { invalidate }=useThrelte();
  const geometry=$derived.by(()=>{
    const pads=points.map(p=>{const g=new RingGeometry(Math.max(0,drill/2),diameter/2,16);g.rotateX(-Math.PI/2);g.translate(p.x,p.y*zScale,p.z);return g;});
    const merged=pads.length?mergeGeometries(pads):new BufferGeometry();pads.forEach(g=>g.dispose());return merged;
  });
  $effect(()=>{const g=geometry;invalidate();return()=>g?.dispose();});
</script>
{#if geometry}<T.Mesh userData={{measureable:true}}><T is={geometry}/><T.MeshBasicMaterial color="#fbbf24" side={DoubleSide}/></T.Mesh>{/if}
