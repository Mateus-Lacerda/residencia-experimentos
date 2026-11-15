/**
 * Modelo intermediário da edificação, independente do dataset (ESPEC.md, seção 4).
 * Cada atributo que não vem da base carrega sua proveniência.
 */

export type DataOrigin = "observed" | "estimated" | "synthetic";

export const ROTULO_ORIGEM: Record<DataOrigin, string> = {
  observed: "real",
  estimated: "estimado",
  synthetic: "sintético",
};

/** Registro bruto exportado por scripts/exportar_dados.py (edificacoes.json). */
export interface BuildingRecord {
  id: string;
  uso: string;
  subUso: string | null;
  area: number;
  andares: number | null;
  anoConstrucao: number | null;
  ocupantes: number | null;
  setor: string | null;
  subsetor: string | null;
  aquecimento: string | null;
  rating: string | null;
  energyStar: number | null;
  euiCadastro: number | null;
  siteEui: number | null;
  sourceEui: number | null;
  leed: string | null;
  medidores: {
    chilledwater: boolean;
    steam: boolean;
    hotwater: boolean;
    gas: boolean;
    water: boolean;
    irrigation: boolean;
    solar: boolean;
  };
  preenchimento: { "2016": number | null; "2017": number | null };
  medianaKwh: { "2016": number | null; "2017": number | null };
}

/** Uma primitiva (caixa) do template da categoria, em coordenadas locais do prédio. */
export interface BuildingPart {
  /** deslocamento do centro da peça em relação ao centro do prédio, antes da rotação */
  dx: number;
  dz: number;
  /** base da peça acima do solo (padrão 0) */
  y?: number;
  width: number;
  depth: number;
  height: number;
}

export interface Building {
  id: string;
  /** nome curto, parte final do id do BDG2 (ex.: "Katelyn") */
  name: string;
  siteId: string;
  usage: string;
  subUsage?: string;
  geometry: {
    width: number;
    depth: number;
    height: number;
    floors?: number;
    estimatedFloors: boolean;
    footprint: number;
    parts: BuildingPart[];
  };
  position: { x: number; z: number; rotation: number };
  attributes: { area: number; yearBuilt?: number; occupants?: number };
  systems: {
    chilledWater: boolean;
    steam: boolean;
    hotWater: boolean;
    gas: boolean;
    water: boolean;
  };
  energy: { actual?: number; predicted?: number; eui?: number; rating?: string };
  /** proveniência por atributo */
  origin: {
    area: DataOrigin;
    floors: DataOrigin;
    height: DataOrigin;
    footprint: DataOrigin;
    position: DataOrigin;
  };
  /** explicação curta da regra usada para a altura */
  heightRule: string;
  record: BuildingRecord;
}

export function nomeCurto(id: string): string {
  const partes = id.split("_");
  return partes[partes.length - 1] ?? id;
}
