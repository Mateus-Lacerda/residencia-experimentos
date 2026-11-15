/**
 * BuildingRenderer: desenha as peças dos prédios com um InstancedMesh por lote de
 * template/uso, gerado uma vez por site. A cor de cada instância é o único estado que muda
 * depois disso (setColors), sem reconstruir geometria.
 */

import * as THREE from "three";
import type { Building } from "../domain/Building.ts";
import type { RGB } from "../utils/colorScale.ts";

interface Batch {
  mesh: THREE.InstancedMesh;
  /** índice do prédio de cada instância */
  owner: Int32Array;
}

export class BuildingRenderer {
  readonly group = new THREE.Group();
  private batches: Batch[] = [];
  private buildings: Building[] = [];
  /** prédio -> instâncias (lote, índice) */
  private instancesOf: { batch: number; index: number }[][] = [];
  private box = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
  private edges = new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0));
  private material = new THREE.MeshLambertMaterial({ color: "#ffffff" });
  private hoverOutline = new THREE.Group();
  private selectOutline = new THREE.Group();
  private hoverMat = new THREE.LineBasicMaterial({ color: "#1f6feb", depthTest: false, transparent: true, opacity: 0.95 });
  private selectMat = new THREE.LineBasicMaterial({ color: "#111418", depthTest: false });
  private tmpColor = new THREE.Color();

  constructor() {
    this.hoverOutline.renderOrder = 10;
    this.selectOutline.renderOrder = 11;
  }

  build(buildings: Building[]) {
    this.buildings = buildings;
    this.instancesOf = buildings.map(() => []);
    // lote por uso: uma chamada de desenho por categoria presente no site
    const porUso = new Map<string, number[]>();
    buildings.forEach((b, i) => {
      if (!porUso.has(b.usage)) porUso.set(b.usage, []);
      porUso.get(b.usage)!.push(i);
    });
    const m = new THREE.Matrix4();
    for (const [, idx] of [...porUso.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
      const total = idx.reduce((a, i) => a + buildings[i].geometry.parts.length, 0);
      const mesh = new THREE.InstancedMesh(this.box, this.material, total);
      const owner = new Int32Array(total);
      const batchId = this.batches.length;
      let k = 0;
      for (const i of idx) {
        const b = buildings[i];
        for (const p of b.geometry.parts) {
          this.partMatrix(b, p, m);
          mesh.setMatrixAt(k, m);
          mesh.setColorAt(k, this.tmpColor.set("#cccccc"));
          owner[k] = i;
          this.instancesOf[i].push({ batch: batchId, index: k });
          k++;
        }
      }
      mesh.instanceMatrix.needsUpdate = true;
      mesh.computeBoundingSphere();
      mesh.computeBoundingBox();
      this.batches.push({ mesh, owner });
      this.group.add(mesh);
    }
    this.group.add(this.hoverOutline, this.selectOutline);
  }

  private partMatrix(b: Building, p: Building["geometry"]["parts"][number], out: THREE.Matrix4) {
    const pos = new THREE.Matrix4().makeTranslation(b.position.x, 0, b.position.z);
    const rot = new THREE.Matrix4().makeRotationY(b.position.rotation);
    const local = new THREE.Matrix4().makeTranslation(p.dx, p.y ?? 0, p.dz);
    const scale = new THREE.Matrix4().makeScale(p.width, p.height, p.depth);
    out.copy(pos).multiply(rot).multiply(local).multiply(scale);
  }

  /** Atualiza só as cores das instâncias (sRGB 0..1 por prédio). */
  setColors(colors: RGB[]) {
    for (let i = 0; i < this.instancesOf.length; i++) {
      const c = colors[i];
      this.tmpColor.setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
      for (const { batch, index } of this.instancesOf[i]) this.batches[batch].mesh.setColorAt(index, this.tmpColor);
    }
    for (const b of this.batches) if (b.mesh.instanceColor) b.mesh.instanceColor.needsUpdate = true;
  }

  /** Índice do prédio sob o raio, ou null. */
  pick(raycaster: THREE.Raycaster): number | null {
    const hits = raycaster.intersectObjects(this.batches.map((b) => b.mesh), false);
    for (const h of hits) {
      if (h.instanceId == null) continue;
      const batch = this.batches.find((b) => b.mesh === h.object);
      if (batch) return batch.owner[h.instanceId];
    }
    return null;
  }

  private outline(group: THREE.Group, mat: THREE.LineBasicMaterial, i: number | null) {
    group.clear();
    if (i == null) return;
    const b = this.buildings[i];
    const m = new THREE.Matrix4();
    for (const p of b.geometry.parts) {
      const seg = new THREE.LineSegments(this.edges, mat);
      this.partMatrix(b, { ...p, width: p.width + 0.6, depth: p.depth + 0.6, height: p.height + 0.3 }, m);
      seg.matrixAutoUpdate = false;
      seg.matrix.copy(m);
      seg.renderOrder = group.renderOrder;
      group.add(seg);
    }
  }

  setHover(i: number | null) {
    this.outline(this.hoverOutline, this.hoverMat, i);
  }

  setSelected(i: number | null) {
    this.outline(this.selectOutline, this.selectMat, i);
  }

  dispose() {
    for (const b of this.batches) b.mesh.dispose();
    this.batches = [];
    this.group.clear();
    this.hoverOutline.clear();
    this.selectOutline.clear();
  }

  disposeShared() {
    this.box.dispose();
    this.edges.dispose();
    this.material.dispose();
    this.hoverMat.dispose();
    this.selectMat.dispose();
  }
}
