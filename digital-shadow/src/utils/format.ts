const nf = (casas: number) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: 0 });

export function fmtNum(v: number | null | undefined, casas = 0): string {
  if (v == null || !Number.isFinite(v)) return "sem dado";
  return nf(casas).format(v);
}

/** Energia com unidade adaptada (kWh, MWh, GWh). */
export function fmtEnergia(kwh: number | null | undefined): string {
  if (kwh == null || !Number.isFinite(kwh)) return "sem dado";
  const a = Math.abs(kwh);
  if (a >= 1e6) return `${fmtNum(kwh / 1e6, 2)} GWh`;
  if (a >= 1e3) return `${fmtNum(kwh / 1e3, 1)} MWh`;
  return `${fmtNum(kwh, 1)} kWh`;
}

export function fmtPct(v: number | null | undefined, casas = 1, sinal = false): string {
  if (v == null || !Number.isFinite(v)) return "sem dado";
  const s = sinal && v > 0 ? "+" : "";
  return `${s}${fmtNum(v, casas)}%`;
}

export function fmtMetric(v: number | null | undefined, unit: string): string {
  if (v == null || !Number.isFinite(v)) return "sem dado";
  if (unit === "kWh") return fmtEnergia(v);
  if (unit === "%") return fmtPct(v, 1, true);
  const casas = Math.abs(v) < 10 ? 2 : Math.abs(v) < 100 ? 1 : 0;
  return `${fmtNum(v, casas)} ${unit}`;
}

/** Valor curto para eixos e legendas. */
export function fmtCurto(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e6) return `${fmtNum(v / 1e6, 1)} mi`;
  if (a >= 1e4) return `${fmtNum(v / 1e3, 0)} mil`;
  if (a >= 1e3) return `${fmtNum(v / 1e3, 1)} mil`;
  if (a >= 10) return fmtNum(v, 0);
  return fmtNum(v, a >= 1 ? 1 : 2);
}
