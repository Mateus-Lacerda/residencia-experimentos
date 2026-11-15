/**
 * RoadGenerator: vias internas e calçadas a partir do arranjo de quadras (synthetic).
 * Vias horizontais entre fileiras, verticais entre quadras da mesma fileira, um anel
 * perimetral e um acesso até a borda do terreno.
 */

import type { Rect } from "../utils/geometry.ts";
import type { SiteLayout } from "./CampusLayoutGenerator.ts";
import { CALCADA, VAO_QUADRAS } from "./CampusLayoutGenerator.ts";

export interface RoadNetwork {
  roads: Rect[];
  sidewalks: Rect[];
  /** faixas de sobra entre o anel viário e quadras de fileiras mais curtas */
  greenFill: Rect[];
}

export function generateRoads(layout: SiteLayout): RoadNetwork {
  const roads: Rect[] = [];
  const sidewalks: Rect[] = [];
  const greenFill: Rect[] = [];
  const e = layout.extent;
  const via = VAO_QUADRAS - 2 * CALCADA;

  // anel perimetral
  const top = e.z - VAO_QUADRAS + CALCADA;
  const bottom = e.z + e.d + CALCADA;
  const left = e.x - VAO_QUADRAS + CALCADA;
  const right = e.x + e.w + CALCADA;
  const fullW = e.w + 2 * (VAO_QUADRAS - CALCADA);
  roads.push({ x: left, z: top, w: fullW, d: via });
  roads.push({ x: left, z: bottom, w: fullW, d: via });
  roads.push({ x: left, z: top, w: via, d: e.d + 2 * (VAO_QUADRAS - CALCADA) });
  roads.push({ x: right, z: top, w: via, d: e.d + 2 * (VAO_QUADRAS - CALCADA) });

  // acesso até a borda do terreno
  const t = layout.terrain;
  roads.push({ x: -via / 2, z: bottom + via, w: via, d: t.z + t.d - (bottom + via) });

  layout.rows.forEach((row, i) => {
    if (i < layout.rows.length - 1) {
      roads.push({ x: left, z: row.z + row.d + CALCADA, w: fullW, d: via });
    }
    const bs = [...row.blocks].sort((a, b) => a.x - b.x);
    for (let k = 0; k < bs.length - 1; k++) {
      const a = bs[k];
      roads.push({ x: a.x + a.w + CALCADA, z: row.z - CALCADA, w: via, d: row.d + 2 * CALCADA });
    }
    // sobra lateral de fileiras centralizadas vira área verde
    const first = bs[0];
    const last = bs[bs.length - 1];
    const sobra = first.x - e.x;
    if (sobra > VAO_QUADRAS + 6) {
      // via de acesso colada à quadra e área verde entre ela e o anel
      roads.push({ x: first.x - VAO_QUADRAS + CALCADA, z: row.z - CALCADA, w: via, d: row.d + 2 * CALCADA });
      roads.push({ x: last.x + last.w + CALCADA, z: row.z - CALCADA, w: via, d: row.d + 2 * CALCADA });
      greenFill.push({ x: e.x, z: row.z, w: sobra - VAO_QUADRAS, d: row.d });
      greenFill.push({ x: last.x + last.w + VAO_QUADRAS, z: row.z, w: sobra - VAO_QUADRAS, d: row.d });
    } else if (sobra > 6) {
      greenFill.push({ x: e.x, z: row.z, w: sobra - CALCADA - 1, d: row.d });
      greenFill.push({ x: last.x + last.w + CALCADA + 1, z: row.z, w: sobra - CALCADA - 1, d: row.d });
    }
  });
  const fills = greenFill.filter((g) => g.w > 3 && g.d > 3);

  for (const b of layout.blocks) {
    const r = b.rect;
    sidewalks.push({ x: r.x - CALCADA, z: r.z - CALCADA, w: r.w + 2 * CALCADA, d: r.d + 2 * CALCADA });
  }
  return { roads, sidewalks, greenFill: fills };
}
