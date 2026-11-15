/**
 * EnergyRenderer: converte o resultado de uma métrica em cores por prédio e aplica no
 * BuildingRenderer. Estado A (sem seleção): todos coloridos pela métrica. Estado B: o
 * selecionado mantém a cor, os demais são dessaturados. Valores ausentes usam a cor de
 * "sem dado", que nunca coincide com o início da escala.
 */

import type { MetricResult } from "../domain/EnergyMetrics.ts";
import type { BuildingRenderer } from "./BuildingRenderer.ts";
import type { ScaleDomain } from "../utils/normalization.ts";
import { normalize } from "../utils/normalization.ts";
import { desaturate, samplePalette, SEM_DADO_RGB, type RGB } from "../utils/colorScale.ts";

export function metricColor(value: number | null, domain: ScaleDomain): RGB {
  if (value == null || !Number.isFinite(value)) return SEM_DADO_RGB;
  return samplePalette(normalize(value, domain), domain.diverging);
}

export class EnergyRenderer {
  private renderer: BuildingRenderer;

  constructor(renderer: BuildingRenderer) {
    this.renderer = renderer;
  }

  apply(result: MetricResult, domain: ScaleDomain, selected: number | null) {
    const cores = result.values.map((v, i) => {
      const c = metricColor(v, domain);
      if (selected == null || i === selected) return c;
      return desaturate(c);
    });
    this.renderer.setColors(cores);
  }
}
