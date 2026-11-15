/**
 * BuildingGenerator: registro do BDG2 -> Building com geometria procedural.
 *
 * Só constrói forma. A aparência energética é responsabilidade do EnergyRenderer, de modo
 * que trocar métrica, período ou previsão nunca reconstrói a geometria.
 *
 * Regras (documentadas no README):
 * - Andares: numberoffloors quando existe (observed); senão
 *   round(sqrt(area / footprintRef[uso])) limitado a [1, maxAndares[uso]] (estimated).
 * - Altura: andares x pé-direito típico do uso. Sempre "estimated", porque o pé-direito
 *   não está na base; a regra registra se os andares eram reais ou estimados.
 * - Footprint: area / andares, com proporção largura:profundidade por categoria (estimated).
 * - Forma: template por categoria, composto por caixas (primitivas reutilizáveis).
 */

import type { Building, BuildingPart, BuildingRecord } from "../domain/Building.ts";
import { nomeCurto } from "../domain/Building.ts";
import { clamp, hashString, seededRandom } from "../utils/geometry.ts";

interface UsageProfile {
  /** pé-direito típico (m) */
  floorHeight: number;
  /** área de pavimento de referência para estimar andares (m²) */
  footprintRef: number;
  maxFloors: number;
  /** proporção largura / profundidade do footprint */
  aspect: number;
  template: TemplateId;
}

type TemplateId = "academico" | "torre" | "lamina" | "hospital" | "auditorio" | "galpao" | "garagem" | "bloco";

const PERFIL_PADRAO: UsageProfile = { floorHeight: 3.5, footprintRef: 1200, maxFloors: 5, aspect: 1.4, template: "bloco" };

export const PERFIS: Record<string, UsageProfile> = {
  Education: { floorHeight: 3.8, footprintRef: 1500, maxFloors: 6, aspect: 1.6, template: "academico" },
  Office: { floorHeight: 3.6, footprintRef: 900, maxFloors: 12, aspect: 1.2, template: "torre" },
  "Public services": { floorHeight: 3.6, footprintRef: 1100, maxFloors: 6, aspect: 1.4, template: "bloco" },
  "Entertainment/public assembly": { floorHeight: 6.0, footprintRef: 3000, maxFloors: 3, aspect: 1.3, template: "auditorio" },
  "Lodging/residential": { floorHeight: 3.0, footprintRef: 700, maxFloors: 10, aspect: 2.6, template: "lamina" },
  Healthcare: { floorHeight: 4.2, footprintRef: 1400, maxFloors: 10, aspect: 1.4, template: "hospital" },
  Parking: { floorHeight: 3.0, footprintRef: 2500, maxFloors: 6, aspect: 1.8, template: "garagem" },
  "Warehouse/storage": { floorHeight: 7.0, footprintRef: 6000, maxFloors: 1, aspect: 1.8, template: "galpao" },
  "Manufacturing/industrial": { floorHeight: 6.5, footprintRef: 5000, maxFloors: 2, aspect: 1.7, template: "galpao" },
  Utility: { floorHeight: 6.0, footprintRef: 3000, maxFloors: 2, aspect: 1.5, template: "galpao" },
  Retail: { floorHeight: 4.5, footprintRef: 2500, maxFloors: 2, aspect: 1.5, template: "bloco" },
  "Food sales and service": { floorHeight: 4.0, footprintRef: 1500, maxFloors: 2, aspect: 1.4, template: "bloco" },
  "Technology/science": { floorHeight: 4.2, footprintRef: 1500, maxFloors: 6, aspect: 1.5, template: "academico" },
  "Religious worship": { floorHeight: 6.0, footprintRef: 1000, maxFloors: 2, aspect: 1.8, template: "auditorio" },
  Services: PERFIL_PADRAO,
  Other: PERFIL_PADRAO,
};

export const perfil = (uso: string) => PERFIS[uso] ?? PERFIL_PADRAO;

/** Peças do template, em frações do footprint (w, d) e da altura (h). */
function templateParts(t: TemplateId, w: number, d: number, h: number, floors: number, rnd: () => number): BuildingPart[] {
  const box = (dx: number, dz: number, pw: number, pd: number, ph: number): BuildingPart => ({
    dx, dz, width: pw, depth: pd, height: Math.max(2.5, ph),
  });
  switch (t) {
    case "academico": {
      // bloco principal + ala em L (pátio aberto no canto)
      if (w * d < 900 || rnd() < 0.25) return [box(0, 0, w, d, h)];
      const ala = 0.42;
      return [
        box(0, -d * (1 - 0.55) / 2, w, d * 0.55, h),
        box(-w * (1 - ala) / 2, d * 0.55 / 2, w * ala, d * 0.45, h * (floors > 1 ? 0.8 : 1)),
      ];
    }
    case "torre": {
      // embasamento baixo + torre recuada quando há altura para isso
      if (floors < 4) return [box(0, 0, w, d, h)];
      const base = Math.min(h, 2 * 3.6);
      return [box(0, 0, w, d, base), box(0, 0, w * 0.62, d * 0.62, h)];
    }
    case "lamina": {
      // duas lâminas paralelas para conjuntos residenciais grandes
      if (w * d < 1200) return [box(0, 0, w, d, h)];
      return [box(0, -d * 0.27, w, d * 0.42, h), box(0, d * 0.27, w, d * 0.42, h)];
    }
    case "hospital": {
      // embasamento largo + bloco de internação mais alto
      if (floors < 3) return [box(0, 0, w, d, h)];
      const base = h * 0.35;
      return [box(0, 0, w, d, base), box(w * 0.12, 0, w * 0.55, d * 0.6, h)];
    }
    case "auditorio": {
      // salão mais baixo + caixa cênica na altura total
      return [box(-w * 0.12, 0, w * 0.76, d, h * 0.7), box(w * 0.38, 0, w * 0.24, d * 0.7, h)];
    }
    case "galpao":
      return [box(0, 0, w, d, h)];
    case "garagem": {
      // pavimentos em lajes separadas (lidas como faixas)
      const n = Math.max(1, floors);
      const fh = h / n;
      const lajes: BuildingPart[] = Array.from({ length: n }, (_, i) => ({
        dx: 0, dz: 0, y: i * fh + fh * 0.45, width: w, depth: d, height: fh * 0.55,
      }));
      return [box(0, 0, w * 0.9, d * 0.9, fh * 0.45 + 0.01), box(-w * 0.4, 0, w * 0.12, d * 0.2, h), ...lajes];
    }
    default:
      return [box(0, 0, w, d, h)];
  }
}

export function estimateFloors(area: number, uso: string): number {
  const p = perfil(uso);
  return clamp(Math.round(Math.sqrt(area / p.footprintRef)), 1, p.maxFloors);
}

export function generateBuilding(rec: BuildingRecord, siteId: string): Building {
  const p = perfil(rec.uso);
  const rnd = seededRandom(hashString(rec.id));
  const temAndares = rec.andares != null && rec.andares > 0;
  const floors = temAndares ? Math.round(rec.andares!) : estimateFloors(rec.area, rec.uso);
  const footprint = rec.area / floors;
  // pequena variação determinística na proporção para não repetir caixas idênticas
  const aspect = p.aspect * (0.85 + rnd() * 0.3);
  const width = Math.sqrt(footprint * aspect);
  const depth = footprint / width;
  const height = floors * p.floorHeight;
  const pd = p.floorHeight.toLocaleString("pt-BR");
  const parts = templateParts(p.template, width, depth, height, floors, rnd);

  return {
    id: rec.id,
    name: nomeCurto(rec.id),
    siteId,
    usage: rec.uso,
    subUsage: rec.subUso ?? undefined,
    geometry: {
      width,
      depth,
      height: Math.max(...parts.map((q) => (q.y ?? 0) + q.height)),
      floors,
      estimatedFloors: !temAndares,
      footprint,
      parts,
    },
    // posição e rotação são preenchidas pelo CampusLayoutGenerator
    position: { x: 0, z: 0, rotation: 0 },
    attributes: {
      area: rec.area,
      yearBuilt: rec.anoConstrucao ?? undefined,
      occupants: rec.ocupantes ?? undefined,
    },
    systems: {
      chilledWater: rec.medidores.chilledwater,
      steam: rec.medidores.steam,
      hotWater: rec.medidores.hotwater,
      gas: rec.medidores.gas,
      water: rec.medidores.water,
    },
    energy: { rating: rec.rating ?? undefined },
    origin: {
      area: "observed",
      floors: temAndares ? "observed" : "estimated",
      height: "estimated",
      footprint: "estimated",
      position: "synthetic",
    },
    heightRule: temAndares
      ? `${floors} andar(es) cadastrado(s) x pé-direito típico de ${pd} m`
      : `${floors} andar(es) estimado(s) por uso e área x pé-direito típico de ${pd} m`,
    record: rec,
  };
}
