import type { DigitalShadowController, ShadowState } from "../controller/DigitalShadowController.ts";
import { METRICAS, metricDef, type MetricId } from "../domain/EnergyMetrics.ts";
import { ROTULO_GRANULARIDADE, type Granularity } from "../domain/Period.ts";
import { ROTULO_ESCALA, type ScaleMode } from "../utils/normalization.ts";
import { fmtEnergia, fmtMetric, fmtNum, fmtPct } from "../utils/format.ts";
import { EnergyLegend } from "./EnergyLegend.tsx";
import { ProvenanceBadge } from "./ProvenanceBadge.tsx";

interface Props {
  state: ShadowState;
  ctl: DigitalShadowController;
}

const GRANULARIDADES: Granularity[] = ["total", "ano", "mes", "semana", "dia"];

export function SiteHeader({ state, ctl }: Props) {
  const { index, site, summary, evaluation, periods, periodIndex } = state;
  const def = metricDef(state.metric);
  const period = periods[periodIndex];
  const temPrev = state.energy?.hasPredictions ?? false;
  const semDado = evaluation ? evaluation.result.values.filter((v) => v == null).length : 0;

  return (
    <header className="cabecalho">
      <div className="cab-linha">
        <div className="cab-site">
          <label className="rotulo-pequeno" htmlFor="sel-site">Site</label>
          <select id="sel-site" value={state.siteId ?? ""} onChange={(e) => ctl.loadSite(e.target.value)}>
            {index?.sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id} ({s.edificacoes} edificações)
              </option>
            ))}
          </select>
          {site && (
            <div className="cab-categoria">
              {site.categoria} <ProvenanceBadge origin="estimated" />
              <span className="cab-sub">
                {site.timezone ?? ""}
                {site.lat != null ? ` · coordenada do site ${fmtNum(site.lat, 2)}, ${fmtNum(site.lng, 2)}` : " · sem coordenada na base"}
              </span>
            </div>
          )}
        </div>

        <div className="cab-kpis">
          <Kpi rotulo="Edificações" valor={fmtNum(site?.edificacoes)} />
          <Kpi
            rotulo="Consumo no período"
            valor={fmtEnergia(summary?.kwh)}
            nota={summary ? `${summary.comDado} prédios com dado; leituras cobrem ${fmtPct(summary.coverage * 100, 1)}` : ""}
            origem={summary?.algumEstimado ? "estimated" : "observed"}
          />
          <Kpi
            rotulo="EUI do site"
            valor={fmtMetric(summary?.eui, "kWh/m²")}
            nota={summary ? `sobre ${fmtNum(summary.areaComDado)} m² com dado` : ""}
            origem={summary?.algumEstimado ? "estimated" : "observed"}
          />
          <Kpi rotulo="Área construída" valor={`${fmtNum(site?.areaTotal)} m²`} origem="observed" />
        </div>
      </div>

      <div className="cab-linha cab-controles">
        <div className="controle">
          <span className="rotulo-pequeno">Período</span>
          <div className="segmentado">
            {GRANULARIDADES.map((g) => (
              <button key={g} className={state.granularity === g ? "ativo" : ""} onClick={() => ctl.setGranularity(g)}>
                {ROTULO_GRANULARIDADE[g]}
              </button>
            ))}
          </div>
        </div>
        <div className="controle controle-tempo">
          <span className="rotulo-pequeno">{period?.label ?? ""}</span>
          <div className="tempo">
            <button onClick={() => ctl.setPeriodIndex(periodIndex - 1)} disabled={periodIndex <= 0} title="Período anterior">Anterior</button>
            <input
              type="range"
              min={0}
              max={Math.max(0, periods.length - 1)}
              value={periodIndex}
              disabled={periods.length < 2}
              onChange={(e) => ctl.setPeriodIndex(Number(e.target.value))}
              aria-label="Deslocar período"
            />
            <button onClick={() => ctl.setPeriodIndex(periodIndex + 1)} disabled={periodIndex >= periods.length - 1} title="Próximo período">Próximo</button>
            <button onClick={() => ctl.togglePlay()} disabled={periods.length < 2} className={state.playing ? "ativo" : ""}>
              {state.playing ? "Pausar" : "Reproduzir"}
            </button>
          </div>
        </div>
        <div className="controle">
          <label className="rotulo-pequeno" htmlFor="sel-metrica">Métrica</label>
          <select id="sel-metrica" value={state.metric} onChange={(e) => ctl.setMetric(e.target.value as MetricId)}>
            {METRICAS.map((m) => (
              <option key={m.id} value={m.id} disabled={m.id === "erro" && !temPrev}>
                {m.label}
                {m.id === "erro" && !temPrev ? " (sem previsões)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="controle">
          <label className="rotulo-pequeno" htmlFor="sel-escala">Escala</label>
          <select id="sel-escala" value={state.scale} onChange={(e) => ctl.setScale(e.target.value as ScaleMode)}>
            {(Object.keys(ROTULO_ESCALA) as ScaleMode[]).map((s) => (
              <option key={s} value={s} disabled={s === "log" && def.diverging}>
                {ROTULO_ESCALA[s]}
              </option>
            ))}
          </select>
        </div>
        <EnergyLegend def={def} domain={evaluation?.domain ?? null} unavailable={evaluation?.result.unavailable ?? null} semDado={semDado} />
      </div>
    </header>
  );
}

function Kpi({ rotulo, valor, nota, origem }: { rotulo: string; valor: string; nota?: string; origem?: "observed" | "estimated" }) {
  return (
    <div className="kpi">
      <div className="rotulo-pequeno">
        {rotulo} {origem && <ProvenanceBadge origin={origem} />}
      </div>
      <div className="kpi-valor">{valor}</div>
      {nota && <div className="kpi-nota">{nota}</div>}
    </div>
  );
}
