/**
 * VegetationGenerator: árvores sintéticas nas áreas verdes e na margem do terreno.
 * Posições determinísticas (semente derivada do id do site).
 */

import type { Rect } from "../utils/geometry.ts";
import { hashString, seededRandom } from "../utils/geometry.ts";

export interface Tree {
  x: number;
  z: number;
  scale: number;
  /** 0 = copa arredondada, 1 = cônica */
  kind: 0 | 1;
}

const MAX_ARVORES = 4000;

function scatter(r: Rect, spacing: number, rnd: () => number, out: Tree[], density = 0.75) {
  if (r.w < 4 || r.d < 4) return;
  const nx = Math.max(1, Math.floor(r.w / spacing));
  const nz = Math.max(1, Math.floor(r.d / spacing));
  const sx = r.w / nx;
  const sz = r.d / nz;
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < nz; j++) {
      if (rnd() > density) continue;
      out.push({
        x: r.x + (i + 0.5) * sx + (rnd() - 0.5) * sx * 0.5,
        z: r.z + (j + 0.5) * sz + (rnd() - 0.5) * sz * 0.5,
        scale: 0.75 + rnd() * 0.6,
        kind: rnd() < 0.7 ? 0 : 1,
      });
    }
  }
}

export function generateVegetation(siteId: string, green: Rect[], terrain: Rect, margin: number): Tree[] {
  const rnd = seededRandom(hashString(`${siteId}:vegetacao`));
  const trees: Tree[] = [];
  for (const g of green) scatter(g, 11, rnd, trees, 0.7);
  // faixas da margem do terreno, fora do anel viário
  const m = margin - 22;
  if (m > 6) {
    const t = terrain;
    const faixas: Rect[] = [
      { x: t.x, z: t.z, w: t.w, d: m },
      { x: t.x, z: t.z + t.d - m, w: t.w / 2 - 14, d: m },
      { x: t.x + t.w / 2 + 14, z: t.z + t.d - m, w: t.w / 2 - 14, d: m },
      { x: t.x, z: t.z + m, w: m, d: t.d - 2 * m },
      { x: t.x + t.w - m, z: t.z + m, w: m, d: t.d - 2 * m },
    ];
    for (const f of faixas) scatter(f, 13, rnd, trees, 0.55);
  }
  if (trees.length > MAX_ARVORES) {
    // amostragem determinística para limitar o custo de renderização
    const passo = trees.length / MAX_ARVORES;
    return Array.from({ length: MAX_ARVORES }, (_, i) => trees[Math.floor(i * passo)]);
  }
  return trees;
}
