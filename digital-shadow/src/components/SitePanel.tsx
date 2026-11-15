import { useMemo } from "react";
import type { ShadowState } from "../controller/DigitalShadowController.ts";
import { metricDef } from "../domain/EnergyMetrics.ts";
import { rotuloUso } from "../domain/Site.ts";
import { metricColor } from "../engine/EnergyRenderer.ts";
import { toCss } from "../utils/colorScale.ts";
import { fmtMetric, fmtNum, fmtPct } from "../utils/format.ts";
import { ProvenanceBadge } from "./ProvenanceBadge.tsx";

/** Painel do estado A (nenhum prédio selecionado): ranking e composição do site. */
export function SitePanel({ state, onSelect }: { state: ShadowState; onSelect: (i: number) => void }) {
  const { model, evaluation, metric } = state;
  const def = metricDef(metric);
  const ranking = useMemo(() => {
    if (!model || !evaluation) return [];
    return model.buildings
      .map((b, i) => ({ b, i, v: evaluation.result.values[i], o: evaluation.result.origins[i] }))
      .sort((a, b) => {
        if (a.v == null && b.v == null) return a.b.name < b.b.name ? -1 : 1;
        if (a.v == null) return 1;
        if (b.v == null) return -1;
        return b.v - a.v;
      });
  }, [model, evaluation]);

  const usos = useMemo(() => {
    const m = new Map<string, number>();
    model?.buildings.forEach((b) => m.set(b.usage, (m.get(b.usage) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [model]);

  if (!model || !evaluation) return null;
  const est = model.buildings.filter((b) => b.geometry.estimatedFloors).length;

  return (
    <aside className="painel">
      <div className="painel-topo">
        <div>
          <div className="painel-sobretitulo">Nenhum prédio selecionado</div>
          <h2>Ranking: {def.label}</h2>
        </div>
      </div>
      <div className="painel-corpo">
        <p className="campo-nota">{def.description} Clique num prédio na cena ou na lista para ver os detalhes.</p>
        {evaluation.result.unavailable && <div className="aviso">{evaluation.result.unavailable}</div>}
        <ol className="ranking">
          {ranking.map(({ b, i, v, o }) => (
            <li key={b.id} onClick={() => onSelect(i)} onMouseDown={(e) => e.preventDefault()}>
              <span className="swatch" style={{ background: toCss(metricColor(v, evaluation.domain)) }} />
              <span className="ranking-nome">
                {b.name}
                <small>{rotuloUso(b.usage)}</small>
              </span>
              <span className="ranking-valor">
                {fmtMetric(v, def.unit)}
                {o === "estimated" && <ProvenanceBadge origin="estimated" />}
              </span>
            </li>
          ))}
        </ol>
        <h3>Composição do site</h3>
        <ul className="composicao">
          {usos.map(([u, n]) => (
            <li key={u}>
              <span>{rotuloUso(u)}</span>
              <span>{n}</span>
            </li>
          ))}
        </ul>
        <h3>Proveniência da cena</h3>
        <ul className="proveniencia">
          <li><ProvenanceBadge origin="observed" /> área construída, uso, consumo de eletricidade, andares em {fmtNum(model.buildings.length - est)} de {fmtNum(model.buildings.length)} prédios ({fmtPct(((model.buildings.length - est) / model.buildings.length) * 100, 0)})</li>
          <li><ProvenanceBadge origin="estimated" /> altura (andares x pé-direito típico), footprint, andares ausentes, totais de períodos com leitura parcial</li>
          <li><ProvenanceBadge origin="synthetic" /> posição dos prédios, terreno, vias, calçadas, árvores e estacionamentos</li>
        </ul>
      </div>
    </aside>
  );
}
