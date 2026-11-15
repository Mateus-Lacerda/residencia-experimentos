/**
 * SceneManager: dono do WebGLRenderer, da cena e dos renderers de terreno e prédios.
 * A geometria do site é gerada uma vez em loadSite(); depois disso só cores e contornos
 * mudam. Renderiza sob demanda: sem mudança, nenhum quadro é desenhado.
 */

import * as THREE from "three";
import type { SiteModel } from "../generators/SiteGenerator.ts";
import type { MetricResult } from "../domain/EnergyMetrics.ts";
import type { ScaleDomain } from "../utils/normalization.ts";
import { BuildingRenderer } from "./BuildingRenderer.ts";
import { CameraManager } from "./CameraManager.ts";
import { EnergyRenderer } from "./EnergyRenderer.ts";
import { InteractionManager, type InteractionCallbacks } from "./InteractionManager.ts";
import { TerrainRenderer } from "./TerrainRenderer.ts";

const PIXEL_RATIO_MAX = 1.5;

export interface SceneStats {
  buildMs: number;
  drawCalls: number;
  triangles: number;
  instances: number;
  lastFrameMs: number;
}

export class SceneManager {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private cameraManager: CameraManager;
  private terrain = new TerrainRenderer();
  private buildings = new BuildingRenderer();
  private energy = new EnergyRenderer(this.buildings);
  private interaction: InteractionManager;
  private resizeObs: ResizeObserver;
  private frame = 0;
  private container: HTMLElement;
  stats: SceneStats = { buildMs: 0, drawCalls: 0, triangles: 0, instances: 0, lastFrameMs: 0 };
  onStats?: (s: SceneStats) => void;

  constructor(container: HTMLElement, cb: InteractionCallbacks) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, PIXEL_RATIO_MAX));
    this.renderer.setClearColor("#eef1f4");
    this.renderer.shadowMap.enabled = false;
    container.appendChild(this.renderer.domElement);

    this.scene.add(new THREE.HemisphereLight("#ffffff", "#8a9a7a", 1.6));
    const sol = new THREE.DirectionalLight("#ffffff", 1.9);
    sol.position.set(-300, 600, 200);
    this.scene.add(sol);
    this.scene.add(this.terrain.group, this.buildings.group);

    this.cameraManager = new CameraManager(this.renderer.domElement, () => this.requestRender());
    this.interaction = new InteractionManager(this.renderer.domElement, this.cameraManager.camera, this.buildings, cb);

    this.resizeObs = new ResizeObserver(() => this.resize());
    this.resizeObs.observe(container);
    this.resize();
  }

  loadSite(model: SiteModel) {
    const t0 = performance.now();
    this.terrain.dispose();
    this.buildings.dispose();
    this.terrain.build(model);
    this.buildings.build(model.buildings);
    this.cameraManager.fit(model.layout.terrain);
    this.stats.buildMs = performance.now() - t0;
    this.stats.instances = model.buildings.reduce((a, b) => a + b.geometry.parts.length, 0);
    this.requestRender();
  }

  applyEnergy(result: MetricResult, domain: ScaleDomain, selected: number | null) {
    this.energy.apply(result, domain, selected);
    this.buildings.setSelected(selected);
    this.requestRender();
  }

  setHover(i: number | null) {
    this.buildings.setHover(i);
    this.renderer.domElement.style.cursor = i == null ? "grab" : "pointer";
    this.requestRender();
  }

  setTreesVisible(v: boolean) {
    this.terrain.setTreesVisible(v);
    this.requestRender();
  }

  resetCamera() {
    this.cameraManager.reset();
    this.requestRender();
  }

  requestRender() {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      const t0 = performance.now();
      this.renderer.render(this.scene, this.cameraManager.camera);
      this.stats.lastFrameMs = performance.now() - t0;
      this.stats.drawCalls = this.renderer.info.render.calls;
      this.stats.triangles = this.renderer.info.render.triangles;
      this.onStats?.({ ...this.stats });
    });
  }

  private resize() {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (w === 0 || h === 0) return;
    this.renderer.setSize(w, h);
    this.cameraManager.setAspect(w / h);
    this.requestRender();
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resizeObs.disconnect();
    this.interaction.dispose();
    this.cameraManager.dispose();
    this.terrain.dispose();
    this.buildings.dispose();
    this.buildings.disposeShared();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
