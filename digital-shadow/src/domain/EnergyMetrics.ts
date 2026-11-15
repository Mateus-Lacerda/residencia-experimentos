/**
 * Métricas energéticas por edificação e período.
 *
 * Regra central: lacuna é ausência de leitura, nunca zero. Toda soma usa apenas as horas
 * observadas e vem acompanhada da cobertura (horas observadas / horas do período).
 *
 * - cobertura = 100%: valor observado (soma direta das leituras).
 * - COBERTURA_MINIMA <= cobertura < 100%: valor estimado = média horária observada x horas
 *   do período (marcado "estimated").
 * - cobertura < COBERTURA_MINIMA: sem dado (categoria visual própria).
 */

import type { DailyEnergyFile } from "./Site.ts";
import type { DataOrigin } from "./Building.ts";
import { periodHours } from "./Period.ts";

export const COBERTURA_MINIMA = 0.5;

export type MetricId = "eui" | "consumo" | "erro" | "desvio" | "variacao";

export interface MetricDef {
  id: MetricId;
  label: string;
  unit: string;
  diverging: boolean;
  description: string;
}

export const METRICAS: MetricDef[] = [
  {
    id: "eui",
    label: "EUI (consumo por área)",
    unit: "kWh/m²",
    diverging: false,
    description: "Consumo de eletricidade no período dividido pela área construída (sqm).",
  },
  {
    id: "consumo",
    label: "Consumo absoluto",
    unit: "kWh",
    diverging: false,
    description: "Consumo de eletricidade no período. Não compara eficiência entre prédios de tamanhos diferentes.",
  },
  {
    id: "erro",
    label: "Erro de previsão",
    unit: "%",
    diverging: true,
    description: "(previsto - real) / real, somente nas horas com leitura e previsão.",
  },
  {
    id: "desvio",
    label: "Desvio da referência",
    unit: "%",
    diverging: true,
    description: "Média horária no período comparada com a média horária do próprio prédio em 2016 e 2017.",
  },
  {
    id: "variacao",
    label: "Variação temporal",
    unit: "%",
    diverging: true,
    description: "Média horária no período comparada com a do período anterior de mesma duração.",
  },
];

export const metricDef = (id: MetricId) => METRICAS.find((m) => m.id === id)!;

/** Somas prefixadas por edificação para consultas de período em O(1). */
export interface EnergyIndex {
  dias: number;
  n: number;
  kwh: Float64Array[];
  horas: Float64Array[];
  prev: null | {
    kwh: Float64Array[];
    horas: Float64Array[];
    parPrev: Float64Array[];
    parReal: Float64Array[];
    parHoras: Float64Array[];
  };
}

function prefixo(arr: (number | null)[]): Float64Array {
  const out = new Float64Array(arr.length + 1);
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    // null não soma nada e não é contado como hora observada (ver prefixo das horas)
    out[i + 1] = out[i] + (v == null ? 0 : v);
  }
  return out;
}

export function buildEnergyIndex(e: DailyEnergyFile): EnergyIndex {
  const p = e.previsao;
  return {
    dias: e.dias,
    n: e.edificacoes.length,
    kwh: e.kwh.map(prefixo),
    horas: e.horas.map(prefixo),
    prev: p
      ? {
          kwh: p.kwh.map(prefixo),
          horas: p.horas.map(prefixo),
          parPrev: p.pareadoPrevisto.map(prefixo),
          parReal: p.pareadoReal.map(prefixo),
          parHoras: p.pareadoHoras.map(prefixo),
        }
      : null,
  };
}

const faixa = (a: Float64Array, s: number, e: number) => a[e + 1] - a[s];

export interface PeriodRange {
  start: number;
  end: number;
}

export interface PeriodConsumption {
  /** soma das leituras existentes (kWh) */
  observedKwh: number;
  observedHours: number;
  totalHours: number;
  coverage: number;
  /** consumo do período para comparação; null se cobertura insuficiente */
  kwh: number | null;
  origin: DataOrigin | null;
  meanKw: number | null;
}

export function consumption(ix: EnergyIndex, b: number, p: PeriodRange): PeriodConsumption {
  const total = periodHours(p);
  if (p.start < 0 || p.end >= ix.dias || p.end < p.start) {
    return { observedKwh: 0, observedHours: 0, totalHours: total, coverage: 0, kwh: null, origin: null, meanKw: null };
  }
  const obs = faixa(ix.kwh[b], p.start, p.end);
  const h = faixa(ix.horas[b], p.start, p.end);
  const cov = h / total;
  if (h === 0 || cov < COBERTURA_MINIMA) {
    return { observedKwh: obs, observedHours: h, totalHours: total, coverage: cov, kwh: null, origin: null, meanKw: h > 0 ? obs / h : null };
  }
  const mean = obs / h;
  const completo = h >= total;
  return {
    observedKwh: obs,
    observedHours: h,
    totalHours: total,
    coverage: cov,
    kwh: completo ? obs : mean * total,
    origin: completo ? "observed" : "estimated",
    meanKw: mean,
  };
}

export interface PeriodPrediction {
  predictedKwh: number | null;
  predictedHours: number;
  /** erro relativo (previsto - real)/real nas horas pareadas, em % */
  errorPct: number | null;
  pairedHours: number;
}

export function prediction(ix: EnergyIndex, b: number, p: PeriodRange): PeriodPrediction {
  if (!ix.prev) return { predictedKwh: null, predictedHours: 0, errorPct: null, pairedHours: 0 };
  const total = periodHours(p);
  const ph = faixa(ix.prev.horas[b], p.start, p.end);
  const pk = faixa(ix.prev.kwh[b], p.start, p.end);
  const parH = faixa(ix.prev.parHoras[b], p.start, p.end);
  const parP = faixa(ix.prev.parPrev[b], p.start, p.end);
  const parR = faixa(ix.prev.parReal[b], p.start, p.end);
  const errorPct = parH / total >= COBERTURA_MINIMA && parR > 0 ? ((parP - parR) / parR) * 100 : null;
  return { predictedKwh: ph > 0 ? pk : null, predictedHours: ph, errorPct, pairedHours: parH };
}

export interface MetricResult {
  metric: MetricId;
  values: (number | null)[];
  origins: (DataOrigin | null)[];
  coverage: number[];
  /** motivo pelo qual a métrica inteira está indisponível, se for o caso */
  unavailable: string | null;
}

export function computeMetric(
  ix: EnergyIndex,
  areas: number[],
  metric: MetricId,
  p: PeriodRange,
): MetricResult {
  const n = ix.n;
  const values: (number | null)[] = new Array(n).fill(null);
  const origins: (DataOrigin | null)[] = new Array(n).fill(null);
  const coverage: number[] = new Array(n).fill(0);
  let unavailable: string | null = null;

  if (metric === "erro" && !ix.prev) {
    unavailable = "Sem previsões importadas para este site. A métrica de erro fica desabilitada.";
  }
  const len = p.end - p.start + 1;
  const anterior = { start: p.start - len, end: p.start - 1 };
  if (metric === "variacao" && anterior.start < 0) {
    unavailable = "Não há período anterior de mesma duração dentro de 2016 e 2017.";
  }
  const tudo = { start: 0, end: ix.dias - 1 };

  for (let b = 0; b < n; b++) {
    const c = consumption(ix, b, p);
    coverage[b] = c.coverage;
    if (unavailable) continue;
    switch (metric) {
      case "consumo":
        values[b] = c.kwh;
        origins[b] = c.origin;
        break;
      case "eui":
        if (c.kwh != null && areas[b] > 0) {
          values[b] = c.kwh / areas[b];
          origins[b] = c.origin;
        }
        break;
      case "erro": {
        const pr = prediction(ix, b, p);
        values[b] = pr.errorPct;
        origins[b] = pr.errorPct == null ? null : "observed";
        break;
      }
      case "desvio": {
        const ref = consumption(ix, b, tudo);
        if (c.meanKw != null && c.kwh != null && ref.kwh != null && ref.meanKw! > 0) {
          // razão entre médias das horas lidas: não extrapola nada, então é "observed"
          // (desde que as duas janelas tenham cobertura mínima)
          values[b] = ((c.meanKw - ref.meanKw!) / ref.meanKw!) * 100;
          origins[b] = "observed";
        }
        break;
      }
      case "variacao": {
        const a = consumption(ix, b, anterior);
        if (c.kwh != null && a.kwh != null && a.meanKw! > 0) {
          values[b] = ((c.meanKw! - a.meanKw!) / a.meanKw!) * 100;
          origins[b] = "observed";
        }
        break;
      }
    }
  }
  return { metric, values, origins, coverage, unavailable };
}

export interface SiteSummary {
  observedKwh: number;
  coverage: number;
  /** soma do consumo comparável (observado ou estimado) dos prédios com dado */
  kwh: number;
  /** área dos prédios que entram em kwh */
  areaComDado: number;
  eui: number | null;
  comDado: number;
  semDado: number;
  algumEstimado: boolean;
}

export function siteSummary(ix: EnergyIndex, areas: number[], p: PeriodRange): SiteSummary {
  let obs = 0;
  let h = 0;
  let kwh = 0;
  let area = 0;
  let comDado = 0;
  let algumEstimado = false;
  for (let b = 0; b < ix.n; b++) {
    const c = consumption(ix, b, p);
    obs += c.observedKwh;
    h += c.observedHours;
    if (c.kwh != null) {
      kwh += c.kwh;
      area += areas[b];
      comDado++;
      if (c.origin === "estimated") algumEstimado = true;
    }
  }
  return {
    observedKwh: obs,
    coverage: h / (ix.n * periodHours(p)),
    kwh,
    areaComDado: area,
    eui: area > 0 && comDado > 0 ? kwh / area : null,
    comDado,
    semDado: ix.n - comDado,
    algumEstimado,
  };
}

/**
 * Série diária comparável para gráficos: dia completo = soma observada; 12 a 23 horas
 * lidas = média horária x 24 (estimado); menos de 12 horas = null (lacuna).
 */
export function dailyComparable(kwh: (number | null)[], horas: number[]): (number | null)[] {
  return kwh.map((v, i) => {
    const h = horas[i];
    if (v == null || h === 0) return null;
    if (h >= 24) return v;
    return h >= 12 ? (v / h) * 24 : null;
  });
}
