/** Retângulo alinhado aos eixos no plano XZ (x, z = canto mínimo). */
export interface Rect {
  x: number;
  z: number;
  w: number;
  d: number;
}

export const rectCenter = (r: Rect) => ({ x: r.x + r.w / 2, z: r.z + r.d / 2 });

export function rectsOverlap(a: Rect, b: Rect, eps = 1e-6): boolean {
  return a.x < b.x + b.w - eps && b.x < a.x + a.w - eps && a.z < b.z + b.d - eps && b.z < a.z + a.d - eps;
}

export function inset(r: Rect, m: number): Rect {
  return { x: r.x + m, z: r.z + m, w: Math.max(0, r.w - 2 * m), d: Math.max(0, r.d - 2 * m) };
}

/** Hash FNV-1a de 32 bits: a mesma string gera sempre o mesmo número. */
export function hashString(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Gerador pseudoaleatório determinístico (mulberry32). */
export function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
