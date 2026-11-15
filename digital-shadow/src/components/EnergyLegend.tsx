import type { MetricDef } from "../domain/EnergyMetrics.ts";
import type { ScaleDomain } from "../utils/normalization.ts";
import { denormalize } from "../utils/normalization.ts";
import { COR_SEM_DADO, paletteCss } from "../utils/colorScale.ts";
import { fmtCurto } from "../utils/format.ts";

interface Props {
  def: MetricDef;
  domain: ScaleDomain | null;
  unavailable: string | null;
  semDado: number;
}

export function EnergyLegend({ def, domain, unavailable, semDado }: Props) {
  if (unavailable || !domain) {
    return (
      <div className="legenda">
        <div className="legenda-indisponivel">{unavailable ?? "Sem valores no período"}</div>
        <LegendaSemDado n={semDado} />
      </div>
    );
  }
  const ticks = domain.diverging ? [0, 0.25, 0.5, 0.75, 1] : [0, 0.5, 1];
  const fmt = (t: number) => {
    const v = denormalize(t, domain);
    return def.unit === "%" ? `${v > 0 ? "+" : ""}${fmtCurto(v)}%` : fmtCurto(v);
  };
  return (
    <div className="legenda">
      <div className="legenda-escala">
        <div className="legenda-barra" style={{ background: paletteCss(domain.diverging) }} />
        <div className="legenda-ticks">
          {ticks.map((t) => (
            <span key={t} style={{ left: `${t * 100}%` }}>
              {fmt(t)}
            </span>
          ))}
        </div>
        <div className="legenda-unidade">
          {def.unit}
          {domain.mode === "quantil" ? " (extremos saturam fora de P5 a P95)" : ""}
        </div>
      </div>
      <LegendaSemDado n={semDado} />
    </div>
  );
}

function LegendaSemDado({ n }: { n: number }) {
  return (
    <div className="legenda-semdado" title="Cobertura de leituras abaixo de 50% no período, ou métrica indisponível">
      <span className="swatch" style={{ background: COR_SEM_DADO }} />
      sem dado ({n})
    </div>
  );
}
