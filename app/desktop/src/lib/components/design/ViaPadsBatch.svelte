<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { annularPadsGeometry, type CopperPad } from "../../viaCopperMesh";
  let { pads, diameter, drill, zScale }: { pads:CopperPad[];diameter:number;drill:number;zScale:number } = $props();
  const { invalidate }=useThrelte();
  const geometry=$derived(annularPadsGeometry(pads,diameter,drill,zScale));
  $effect(()=>{const g=geometry;invalidate();return()=>g?.dispose();});
</script>
{#if geometry}<T.Mesh userData={{measureable:true}}><T is={geometry}/><T.MeshStandardMaterial color="#fbbf24" roughness={0.5} metalness={0.25}/></T.Mesh>{/if}
