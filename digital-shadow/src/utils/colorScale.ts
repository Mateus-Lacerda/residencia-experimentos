/** Paletas de cor da camada energética. Cores em sRGB 0..1 (convertidas no Three.js). */

export type RGB = [number, number, number];

const hex = (h: string): RGB => {
  const n = parseInt(h.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};

/** Sequencial (baixo -> alto consumo): amarelo claro a vermelho escuro (YlOrRd sem o tom mais claro, para não confundir com o piso). */
export const SEQUENCIAL = ["#fff2a8", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"];
/** Divergente centrada em zero: azul (abaixo) - branco - vermelho (acima). */
export const DIVERGENTE = ["#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b"];

/** Cor fixa de "sem dado": categoria visual própria, fora das duas paletas. */
export const COR_SEM_DADO = "#8a8f98";

const SEQ_RGB = SEQUENCIAL.map(hex);
const DIV_RGB = DIVERGENTE.map(hex);
export const SEM_DADO_RGB = hex(COR_SEM_DADO);

export function samplePalette(t: number, diverging: boolean): RGB {
  const stops = diverging ? DIV_RGB : SEQ_RGB;
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

export function toCss(c: RGB): string {
  const h = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0");
  return `#${h(c[0])}${h(c[1])}${h(c[2])}`;
}

/** Dessatura e clareia a cor (prédios não selecionados no estado B). */
export function desaturate(c: RGB, amount = 0.8, lighten = 0.35): RGB {
  const l = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2];
  const g = (v: number) => v + (l - v) * amount;
  const k = (v: number) => v + (0.92 - v) * lighten;
  return [k(g(c[0])), k(g(c[1])), k(g(c[2]))];
}

export function paletteCss(diverging: boolean): string {
  const stops = diverging ? DIVERGENTE : SEQUENCIAL;
  return `linear-gradient(to right, ${stops.map((s, i) => `${s} ${(i / (stops.length - 1)) * 100}%`).join(", ")})`;
}
