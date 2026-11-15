/** Normalização de valores para a escala de cores. Valores null ficam fora do cálculo. */

export type ScaleMode = "quantil" | "minmax" | "log";

export const ROTULO_ESCALA: Record<ScaleMode, string> = {
  quantil: "Percentis 5 a 95",
  minmax: "Mínimo a máximo",
  log: "Logarítmica",
};

export interface ScaleDomain {
  mode: ScaleMode;
  min: number;
  max: number;
  diverging: boolean;
  /** quantos valores válidos entraram no domínio */
  count: number;
}

export function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export function computeDomain(values: (number | null)[], mode: ScaleMode, diverging: boolean): ScaleDomain {
  const v = values.filter((x): x is number => x != null && Number.isFinite(x));
  if (v.length === 0) return { mode, min: 0, max: 1, diverging, count: 0 };
  if (diverging) {
    // centrada em zero: limite simétrico pelo maior desvio absoluto (ou P95 dele)
    const abs = v.map(Math.abs).sort((a, b) => a - b);
    let m = mode === "quantil" ? quantile(abs, 0.95) : abs[abs.length - 1];
    if (!(m > 0)) m = 1;
    return { mode, min: -m, max: m, diverging, count: v.length };
  }
  const s = [...v].sort((a, b) => a - b);
  let min = mode === "quantil" ? quantile(s, 0.05) : s[0];
  let max = mode === "quantil" ? quantile(s, 0.95) : s[s.length - 1];
  if (mode === "log") {
    const pos = s.filter((x) => x > 0);
    min = pos.length ? pos[0] : 1;
    max = pos.length ? pos[pos.length - 1] : 10;
  }
  if (max <= min) max = min + (Math.abs(min) || 1);
  return { mode, min, max, diverging, count: v.length };
}

/** Converte valor em t no intervalo [0, 1] (0.5 = zero nas escalas divergentes). */
export function normalize(value: number, d: ScaleDomain): number {
  let t: number;
  if (d.mode === "log" && !d.diverging) {
    const v = Math.max(value, d.min);
    t = (Math.log(v) - Math.log(d.min)) / (Math.log(d.max) - Math.log(d.min));
  } else {
    t = (value - d.min) / (d.max - d.min);
  }
  return Math.min(1, Math.max(0, t));
}

/** Valor correspondente a t (inverso de normalize), usado nos ticks da legenda. */
export function denormalize(t: number, d: ScaleDomain): number {
  if (d.mode === "log" && !d.diverging) {
    return Math.exp(Math.log(d.min) + t * (Math.log(d.max) - Math.log(d.min)));
  }
  return d.min + t * (d.max - d.min);
}
