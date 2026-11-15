/**
 * EnergyManager: recebe período e métrica, calcula os valores (EnergyMetrics) e normaliza
 * para a escala de cores. Não sabe nada de Three.js; o EnergyRenderer aplica o resultado.
 */

import type { DailyEnergyFile } from "../domain/Site.ts";
import {
  buildEnergyIndex,
  computeMetric,
  metricDef,
  type EnergyIndex,
  type MetricId,
  type MetricResult,
  type PeriodRange,
} from "../domain/EnergyMetrics.ts";
import { computeDomain, type ScaleDomain, type ScaleMode } from "../utils/normalization.ts";

export interface EnergyState {
  result: MetricResult;
  domain: ScaleDomain;
}

export class EnergyManager {
  readonly index: EnergyIndex;
  readonly areas: number[];

  constructor(energy: DailyEnergyFile, areas: number[]) {
    this.index = buildEnergyIndex(energy);
    this.areas = areas;
  }

  get hasPredictions() {
    return this.index.prev != null;
  }

  evaluate(metric: MetricId, period: PeriodRange, scale: ScaleMode): EnergyState {
    const result = computeMetric(this.index, this.areas, metric, period);
    const def = metricDef(metric);
    const domain = computeDomain(result.values, def.diverging && scale === "log" ? "minmax" : scale, def.diverging);
    return { result, domain };
  }
}
