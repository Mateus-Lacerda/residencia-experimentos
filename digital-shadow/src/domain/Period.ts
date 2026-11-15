/**
 * Períodos de análise, em índices de dia a partir de 2016-01-01 (inclusive nas duas pontas).
 * Datas tratadas em UTC para não depender do fuso do navegador; os timestamps do BDG2 já
 * estão no horário local de cada site.
 */

export type Granularity = "total" | "ano" | "mes" | "semana" | "dia";

export interface Period {
  granularity: Granularity;
  start: number;
  end: number;
  label: string;
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

export const ROTULO_GRANULARIDADE: Record<Granularity, string> = {
  total: "2016 a 2017",
  ano: "Ano",
  mes: "Mês",
  semana: "Semana",
  dia: "Dia",
};

export function dayToDate(inicio: string, day: number): Date {
  const d = new Date(`${inicio}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + day);
  return d;
}

export function fmtDia(d: Date): string {
  return `${String(d.getUTCDate()).padStart(2, "0")}/${MESES[d.getUTCMonth()]}/${d.getUTCFullYear()}`;
}

export function fmtMesCurto(d: Date): string {
  return `${MESES[d.getUTCMonth()]}/${String(d.getUTCFullYear()).slice(2)}`;
}

/** Lista as janelas da granularidade dentro do intervalo de dias disponível. */
export function buildPeriods(inicio: string, dias: number, g: Granularity): Period[] {
  const out: Period[] = [];
  if (g === "total") {
    const a = dayToDate(inicio, 0);
    const b = dayToDate(inicio, dias - 1);
    return [{ granularity: g, start: 0, end: dias - 1, label: `${fmtDia(a)} a ${fmtDia(b)}` }];
  }
  if (g === "dia") {
    for (let i = 0; i < dias; i++) {
      const d = dayToDate(inicio, i);
      out.push({ granularity: g, start: i, end: i, label: fmtDia(d) });
    }
    return out;
  }
  if (g === "semana") {
    for (let i = 0; i + 6 < dias; i += 7) {
      const a = dayToDate(inicio, i);
      const b = dayToDate(inicio, i + 6);
      out.push({ granularity: g, start: i, end: i + 6, label: `${fmtDia(a)} a ${fmtDia(b)}` });
    }
    return out;
  }
  // ano e mês: agrupa pelos dias reais do calendário
  let cur: Period | null = null;
  for (let i = 0; i < dias; i++) {
    const d = dayToDate(inicio, i);
    const label =
      g === "ano" ? String(d.getUTCFullYear()) : `${MESES_LONGOS[d.getUTCMonth()]} de ${d.getUTCFullYear()}`;
    if (!cur || cur.label !== label) {
      cur = { granularity: g, start: i, end: i, label };
      out.push(cur);
    } else {
      cur.end = i;
    }
  }
  return out;
}

export const periodDays = (p: { start: number; end: number }) => p.end - p.start + 1;
export const periodHours = (p: { start: number; end: number }) => periodDays(p) * 24;
