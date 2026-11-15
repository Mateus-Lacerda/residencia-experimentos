/**
 * CameraManager: câmera ortográfica em perspectiva isométrica.
 * Arrastar rotaciona (OrbitControls), scroll aplica zoom, botão direito desloca.
 */

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Rect } from "../utils/geometry.ts";

// isometria verdadeira: azimute de 45 graus, elevação de atan(1/sqrt(2)) ~ 35,26 graus
const ELEVACAO = Math.atan(1 / Math.SQRT2);
const AZIMUTE = Math.PI / 4;

export class CameraManager {
  readonly camera: THREE.OrthographicCamera;
  readonly controls: OrbitControls;
  private halfExtent = 200;
  private aspect = 1;
  private distance = 1500;

  constructor(dom: HTMLElement, onChange: () => void) {
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 10000);
    this.controls = new OrbitControls(this.camera, dom);
    this.controls.enableDamping = false;
    this.controls.screenSpacePanning = false;
    this.controls.minPolarAngle = 0.15;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.12;
    this.controls.minZoom = 0.4;
    this.controls.maxZoom = 14;
    this.controls.zoomToCursor = true;
    this.controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };
    this.controls.addEventListener("change", onChange);
  }

  /** Ajusta o enquadramento para o terreno do site. */
  fit(terrain: Rect) {
    // raio do terreno projetado; folga para o painel não cortar as bordas
    this.halfExtent = Math.hypot(terrain.w, terrain.d) * 0.42;
    this.distance = Math.max(terrain.w, terrain.d) * 2 + 500;
    this.camera.far = this.distance * 4;
    this.reset();
  }

  reset() {
    const d = this.distance;
    const t = new THREE.Vector3(0, 0, 0);
    this.camera.position.set(
      t.x + d * Math.cos(ELEVACAO) * Math.sin(AZIMUTE),
      t.y + d * Math.sin(ELEVACAO),
      t.z + d * Math.cos(ELEVACAO) * Math.cos(AZIMUTE),
    );
    this.camera.zoom = 1;
    this.controls.target.copy(t);
    this.updateFrustum();
    this.controls.update();
  }

  setAspect(aspect: number) {
    this.aspect = aspect;
    this.updateFrustum();
  }

  private updateFrustum() {
    const h = this.halfExtent;
    const a = this.aspect;
    // garante que o terreno caiba tanto na largura quanto na altura
    const halfH = a >= 1 ? h * 0.72 : (h * 0.72) / a;
    this.camera.left = -halfH * a;
    this.camera.right = halfH * a;
    this.camera.top = halfH;
    this.camera.bottom = -halfH;
    this.camera.updateProjectionMatrix();
  }

  dispose() {
    this.controls.dispose();
  }
}
