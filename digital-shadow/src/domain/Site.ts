import type { BuildingRecord } from "./Building.ts";

export interface SiteInfo {
  id: string;
  edificacoes: number;
  /** categoria inferida do uso dominante (estimated) */
  categoria: string;
  usoDominante: string;
  areaTotal: number;
  timezone: string | null;
  lat: number | null;
  lng: number | null;
  previsoes?: boolean;
}

export interface SitesIndex {
  fonte: string;
  periodo: { inicio: string; fim: string };
  totalEdificacoes: number;
  sites: SiteInfo[];
}

export interface SiteBuildingsFile {
  site: SiteInfo;
  edificacoes: BuildingRecord[];
}

/** Bloco de previsões agregadas por dia (presente só se previsoes/<Site>.csv existir). */
export interface DailyPredictions {
  kwh: (number | null)[][];
  horas: number[][];
  /** soma prevista apenas nas horas que também têm leitura real */
  pareadoPrevisto: (number | null)[][];
  /** soma real apenas nas horas que também têm previsão */
  pareadoReal: (number | null)[][];
  pareadoHoras: number[][];
}

export interface DailyEnergyFile {
  site: string;
  inicio: string;
  dias: number;
  unidade: "kWh";
  edificacoes: string[];
  /** soma diária das horas observadas; null = nenhuma leitura no dia */
  kwh: (number | null)[][];
  /** horas observadas no dia (0 a 24) */
  horas: number[][];
  previsao: DailyPredictions | null;
  clima: { temperaturaMedia: (number | null)[]; origem: "observed" } | null;
}

export interface HourlyEnergyFile {
  id: string;
  inicio: string;
  horas: number;
  kwh: (number | null)[];
  previsto: (number | null)[] | null;
}

const BASE = `${import.meta.env.BASE_URL}data`;

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Falha ao carregar ${url}: ${r.status}`);
  return (await r.json()) as T;
}

export const carregarIndice = () => getJson<SitesIndex>(`${BASE}/sites.json`);
export const carregarEdificacoes = (site: string) =>
  getJson<SiteBuildingsFile>(`${BASE}/sites/${site}/edificacoes.json`);
export const carregarEnergiaDiaria = (site: string) =>
  getJson<DailyEnergyFile>(`${BASE}/sites/${site}/energia_diaria.json`);

const cacheHorario = new Map<string, Promise<HourlyEnergyFile>>();
export function carregarHorario(site: string, id: string): Promise<HourlyEnergyFile> {
  const chave = `${site}/${id}`;
  let p = cacheHorario.get(chave);
  if (!p) {
    p = getJson<HourlyEnergyFile>(`${BASE}/sites/${site}/horario/${id}.json`);
    p.catch(() => cacheHorario.delete(chave));
    cacheHorario.set(chave, p);
  }
  return p;
}

export const ROTULO_USO: Record<string, string> = {
  Education: "Educação",
  Office: "Escritório",
  "Public services": "Serviços públicos",
  "Entertainment/public assembly": "Entretenimento e reunião pública",
  "Lodging/residential": "Hospedagem e residencial",
  Healthcare: "Saúde",
  Parking: "Estacionamento",
  "Warehouse/storage": "Depósito e armazenagem",
  Other: "Outros",
  Services: "Serviços",
  "Manufacturing/industrial": "Manufatura e indústria",
  Retail: "Varejo",
  "Food sales and service": "Alimentação",
  "Technology/science": "Tecnologia e ciência",
  "Religious worship": "Culto religioso",
  Utility: "Utilidades",
};

export const rotuloUso = (u: string) => ROTULO_USO[u] ?? u;
