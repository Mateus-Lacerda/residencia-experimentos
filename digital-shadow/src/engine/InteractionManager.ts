/**
 * InteractionManager: hover e clique com Raycaster (instanceId -> prédio).
 * Clique só conta se o ponteiro quase não se moveu, para não conflitar com o arrasto
 * da câmera. Clique fora dos prédios limpa a seleção.
 */

import * as THREE from "three";
import type { BuildingRenderer } from "./BuildingRenderer.ts";

export interface InteractionCallbacks {
  onHover(index: number | null, clientX: number, clientY: number): void;
  onSelect(index: number | null): void;
}

const TOLERANCIA_CLIQUE = 5;

export class InteractionManager {
  private raycaster = new THREE.Raycaster();
  private ndc = new THREE.Vector2();
  private down: { x: number; y: number } | null = null;
  private pending: PointerEvent | null = null;
  private frame = 0;
  private hovered: number | null = null;
  private dom: HTMLElement;
  private camera: THREE.Camera;
  private buildings: BuildingRenderer;
  private cb: InteractionCallbacks;

  constructor(dom: HTMLElement, camera: THREE.Camera, buildings: BuildingRenderer, cb: InteractionCallbacks) {
    this.dom = dom;
    this.camera = camera;
    this.buildings = buildings;
    this.cb = cb;
    dom.addEventListener("pointerdown", this.onDown);
    dom.addEventListener("pointerup", this.onUp);
    dom.addEventListener("pointermove", this.onMove);
    dom.addEventListener("pointerleave", this.onLeave);
  }

  private pick(e: PointerEvent): number | null {
    const r = this.dom.getBoundingClientRect();
    this.ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(this.ndc, this.camera);
    return this.buildings.pick(this.raycaster);
  }

  private onDown = (e: PointerEvent) => {
    if (e.button === 0) this.down = { x: e.clientX, y: e.clientY };
  };

  private onUp = (e: PointerEvent) => {
    if (e.button !== 0 || !this.down) return;
    const moved = Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y);
    this.down = null;
    if (moved > TOLERANCIA_CLIQUE) return;
    this.cb.onSelect(this.pick(e));
  };

  private onMove = (e: PointerEvent) => {
    // durante o arrasto não faz raycast de hover
    if (e.buttons !== 0) return;
    this.pending = e;
    if (!this.frame) {
      this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        const ev = this.pending;
        if (!ev) return;
        const i = this.pick(ev);
        if (i !== this.hovered || i != null) {
          this.hovered = i;
          this.cb.onHover(i, ev.clientX, ev.clientY);
        }
      });
    }
  };

  private onLeave = () => {
    this.pending = null;
    if (this.hovered != null) {
      this.hovered = null;
      this.cb.onHover(null, 0, 0);
    }
  };

  dispose() {
    cancelAnimationFrame(this.frame);
    this.dom.removeEventListener("pointerdown", this.onDown);
    this.dom.removeEventListener("pointerup", this.onUp);
    this.dom.removeEventListener("pointermove", this.onMove);
    this.dom.removeEventListener("pointerleave", this.onLeave);
  }
}
