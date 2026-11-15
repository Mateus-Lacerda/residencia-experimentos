/**
 * TerrainRenderer: terreno, vias, calçadas, áreas verdes, estacionamentos e árvores.
 * Tudo sintético. Cada camada é um único InstancedMesh (uma chamada de desenho por camada).
 */

import * as THREE from "three";
import type { SiteModel } from "../generators/SiteGenerator.ts";
import type { Rect } from "../utils/geometry.ts";

const CORES = {
  terreno: "#b9c99a",
  base: "#8d7f68",
  verde: "#9fbb7f",
  lote: "#c6c2b6",
  calcada: "#d6d2c8",
  caminho: "#dcd7ca",
  via: "#5d636b",
  estacionamento: "#7b8189",
  faixa: "#f2f2ee",
  tronco: "#7a5a3c",
  copa: "#5f8f4e",
  copaConica: "#4f7d48",
};

const MAX_FAIXAS = 12000;

export class TerrainRenderer {
  readonly group = new THREE.Group();
  /** malha do chão, usada pelo raycast para "clique no terreno" */
  ground!: THREE.Mesh;
  private disposables: { dispose(): void }[] = [];
  private treeMeshes: THREE.InstancedMesh[] = [];

  build(model: SiteModel) {
    const t = model.layout.terrain;
    const plano = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    this.disposables.push(plano);

    // laje do terreno com espessura (efeito de maquete)
    const baseGeo = new THREE.BoxGeometry(t.w, 6, t.d);
    const baseMat = this.mat(CORES.base);
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.position.set(t.x + t.w / 2, -3.01, t.z + t.d / 2);
    this.disposables.push(baseGeo);
    this.group.add(base);

    const chaoMat = this.mat(CORES.terreno);
    const chao = new THREE.Mesh(plano, chaoMat);
    chao.scale.set(t.w, 1, t.d);
    chao.position.set(t.x + t.w / 2, 0, t.z + t.d / 2);
    chao.name = "terreno";
    this.ground = chao;
    this.group.add(chao);

    const { layout, roads } = model;
    this.layer(plano, [...layout.green, ...roads.greenFill], CORES.verde, 0.2);
    this.layer(plano, roads.sidewalks, CORES.calcada, 0.4);
    this.layer(plano, layout.lots.map((l) => ({ x: l.x + 1, z: l.z + 1, w: l.w - 2, d: l.d - 2 })), CORES.lote, 0.55);
    this.layer(plano, layout.paths, CORES.caminho, 0.6);
    this.layer(plano, roads.roads, CORES.via, 0.7);
    this.layer(plano, layout.parking.map((p) => p.rect), CORES.estacionamento, 0.8);

    // faixas das vagas (2,5 m de largura, 5 m de profundidade)
    const faixas: Rect[] = [];
    for (const p of layout.parking) {
      const n = Math.floor(p.rect.w / 2.5);
      const blocos = p.rows / 2; // cada bloco: fileira + corredor + fileira
      for (let b = 0; b < blocos && faixas.length < MAX_FAIXAS; b++) {
        const z0 = p.rect.z + b * 16;
        for (let i = 0; i <= n; i++) {
          const x = p.rect.x + i * 2.5;
          faixas.push({ x: x - 0.08, z: z0 + 0.3, w: 0.16, d: 4.6 });
          faixas.push({ x: x - 0.08, z: z0 + 11.1, w: 0.16, d: 4.6 });
        }
      }
    }
    this.layer(plano, faixas.slice(0, MAX_FAIXAS), CORES.faixa, 0.9);
    this.trees(model);
  }

  private mat(cor: string) {
    const m = new THREE.MeshLambertMaterial({ color: cor });
    this.disposables.push(m);
    return m;
  }

  private layer(geo: THREE.BufferGeometry, rects: Rect[], cor: string, y: number) {
    if (rects.length === 0) return;
    const mesh = new THREE.InstancedMesh(geo, this.mat(cor), rects.length);
    const m = new THREE.Matrix4();
    rects.forEach((r, i) => {
      m.makeScale(Math.max(r.w, 0.01), 1, Math.max(r.d, 0.01));
      m.setPosition(r.x + r.w / 2, y, r.z + r.d / 2);
      mesh.setMatrixAt(i, m);
    });
    mesh.computeBoundingSphere();
    mesh.matrixAutoUpdate = false;
    this.group.add(mesh);
  }

  private trees(model: SiteModel) {
    const ts = model.trees;
    if (ts.length === 0) return;
    const tronco = new THREE.CylinderGeometry(0.35, 0.45, 3, 5).translate(0, 1.5, 0);
    const copa = new THREE.IcosahedronGeometry(2.8, 0).translate(0, 5, 0);
    const cone = new THREE.ConeGeometry(2.4, 7, 6).translate(0, 6, 0);
    this.disposables.push(tronco, copa, cone);
    const redondas = ts.filter((t) => t.kind === 0);
    const conicas = ts.filter((t) => t.kind === 1);
    const make = (geo: THREE.BufferGeometry, cor: string, lista: typeof ts) => {
      if (!lista.length) return;
      const mesh = new THREE.InstancedMesh(geo, this.mat(cor), lista.length);
      const m = new THREE.Matrix4();
      lista.forEach((t, i) => {
        m.makeScale(t.scale, t.scale, t.scale);
        m.setPosition(t.x, 0, t.z);
        mesh.setMatrixAt(i, m);
      });
      mesh.computeBoundingSphere();
      this.treeMeshes.push(mesh);
      this.group.add(mesh);
    };
    make(tronco, CORES.tronco, ts);
    make(copa, CORES.copa, redondas);
    make(cone, CORES.copaConica, conicas);
  }

  setTreesVisible(v: boolean) {
    for (const m of this.treeMeshes) m.visible = v;
  }

  dispose() {
    this.disposables.forEach((d) => d.dispose());
    this.disposables = [];
    this.treeMeshes = [];
    this.group.clear();
  }
}
