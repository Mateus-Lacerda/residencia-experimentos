import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { Building, DataOrigin } from "../domain/Building.ts";
import type { HourlyEnergyFile } from "../domain/Site.ts";
import { carregarHorario, rotuloUso } from "../domain/Site.ts";
import { buildPeriods, dayToDate, fmtDia, fmtMesCurto, periodDays, type Period } from "../domain/Period.ts";
import { consumption, COBERTURA_MINIMA, dailyComparable, metricDef, prediction } from "../domain/EnergyMetrics.ts";
import type { ShadowState } from "../controller/DigitalShadowController.ts";
import { ProvenanceBadge } from "./ProvenanceBadge.tsx";
import { LineChart, type Series } from "./charts/LineChart.tsx";
import { BarChart } from "./charts/BarChart.tsx";
import { fmtEnergia, fmtMetric, fmtNum, fmtPct } from "../utils/format.ts";

type Aba = "geral" | "historico" | "previsao" | "construtivo" | "sistemas";

const ABAS: { id: Aba; label: string }[] = [
  { id: "geral", label: "Visão geral" },
  { id: "historico", label: "Histórico energético" },
  { id: "previsao", label: "Previsão" },
  { id: "construtivo", label: "Características construtivas" },
  { id: "sistemas", label: "Sistemas e medidores" },
];

interface Props {
  state: ShadowState;
  building: Building;
  index: number;
  period: Period;
  onClose: () => void;
  onPickPeriod: (granularity: "mes", start: number) => void;
}

const COR_REAL = "#1f4e79";
const COR_PREV = "#d6604d";

export function BuildingPanel({ state, building, index, period, onClose, onPickPeriod }: Props) {
  const [aba, setAba] = useState<Aba>("geral");
  const [horario, setHorario] = useState<HourlyEnergyFile | null>(null);
  const [erroHorario, setErroHorario] = useState<string | null>(null);
  const energy = state.energy!;
  const ef = state.energyFile!;

  useEffect(() => {
    let vivo = true;
    setHorario(null);
    setErroHorario(null);
    carregarHorario(building.siteId, building.id)
      .then((h) => vivo && setHorario(h))
      .catch((e: Error) => vivo && setErroHorario(e.message));
    return () => {
      vivo = false;
    };
  }, [building.siteId, building.id]);

  const c = consumption(energy.index, index, period);
  const pr = prediction(energy.index, index, period);
  const eui = c.kwh != null ? c.kwh / building.attributes.area : null;
  const def = metricDef(state.metric);
  const valorMetrica = state.evaluation?.result.values[index] ?? null;
  const origemMetrica = state.evaluation?.result.origins[index] ?? null;

  return (
    <aside className="painel">
      <div className="painel-topo">
        <div>
          <div className="painel-sobretitulo">{rotuloUso(building.usage)}{building.subUsage ? ` / ${building.subUsage}` : ""}</div>
          <h2>{building.name}</h2>
          <div className="painel-id">{building.id}</div>
        </div>
        <button className="botao-fechar" onClick={onClose} title="Remover seleção">Fechar</button>
      </div>
      <nav className="abas">
        {ABAS.map((a) => (
          <button key={a.id} className={aba === a.id ? "ativa" : ""} onClick={() => setAba(a.id)}>
            {a.label}
          </button>
        ))}
      </nav>
      <div className="painel-corpo">
        {aba === "geral" && (
          <>
            <Campos>
              <Campo rotulo="Uso" valor={rotuloUso(building.usage)} origem="observed" />
              <Campo rotulo="Uso detalhado" valor={building.subUsage ?? null} origem={building.subUsage ? "observed" : null} />
              <Campo
                rotulo={`Consumo no período (${period.label})`}
                valor={fmtEnergia(c.kwh)}
                origem={c.origin}
                nota={notaCobertura(c.coverage, c.observedKwh)}
              />
              <Campo
                rotulo="Consumo previsto"
                valor={pr.predictedKwh != null ? fmtEnergia(pr.predictedKwh) : "sem previsão"}
                origem={pr.predictedKwh != null ? "observed" : null}
                nota={pr.predictedKwh != null ? `${fmtNum(pr.predictedHours)} h com previsão` : "Nenhuma previsão do modelo importada"}
              />
              <Campo rotulo="EUI no período" valor={fmtMetric(eui, "kWh/m²")} origem={c.origin} />
              <Campo rotulo={`Métrica do mapa: ${def.label}`} valor={fmtMetric(valorMetrica, def.unit)} origem={origemMetrica} />
              <Campo rotulo="Área construída" valor={`${fmtNum(building.attributes.area)} m²`} origem="observed" />
              <Campo
                rotulo="Andares"
                valor={fmtNum(building.geometry.floors)}
                origem={building.origin.floors}
                nota={building.geometry.estimatedFloors ? "Estimado por uso e área" : undefined}
              />
            </Campos>
            <h3>Real x previsto no período</h3>
            <GraficoPeriodo state={state} index={index} period={period} horario={horario} erro={erroHorario} />
          </>
        )}
        {aba === "historico" && (
          <Historico state={state} index={index} period={period} horario={horario} building={building} onPickPeriod={onPickPeriod} />
        )}
        {aba === "previsao" && (
          <>
            {!energy.hasPredictions ? (
              <div className="aviso">
                <strong>Sem previsão.</strong> Ainda não há previsões do modelo para este site. Quando existirem,
                coloque <code>previsoes/{building.siteId}.csv</code> com as colunas <code>edificacao,timestamp,previsto_kwh</code>
                {" "}(uma linha por hora, timestamp no mesmo formato do BDG2) e rode <code>npm run dados</code>. A métrica de
                erro de previsão fica desabilitada até lá.
              </div>
            ) : (
              <Campos>
                <Campo rotulo="Consumo previsto" valor={fmtEnergia(pr.predictedKwh)} origem={pr.predictedKwh != null ? "observed" : null} />
                <Campo rotulo="Erro relativo (horas pareadas)" valor={fmtPct(pr.errorPct, 1, true)} origem={pr.errorPct != null ? "observed" : null} />
                <Campo rotulo="Horas com leitura e previsão" valor={fmtNum(pr.pairedHours)} origem="observed" />
              </Campos>
            )}
            <h3>Real x previsto</h3>
            <GraficoPeriodo state={state} index={index} period={period} horario={horario} erro={erroHorario} />
          </>
        )}
        {aba === "construtivo" && <Construtivo b={building} />}
        {aba === "sistemas" && <Sistemas b={building} />}
      </div>
      <div className="painel-rodape">
        Período: {period.label}. Origem: dados {ef.unidade} horários do BDG2 (eletricidade).
      </div>
    </aside>
  );
}

function notaCobertura(cov: number, obs: number) {
  const pct = fmtPct(cov * 100, 1);
  if (cov >= 1) return `Cobertura de leituras: 100%`;
  if (cov < COBERTURA_MINIMA) return `Cobertura de ${pct}: insuficiente (abaixo de 50%). Lido: ${fmtEnergia(obs)}`;
  return `Cobertura de ${pct}: total estimado pela média horária observada. Lido: ${fmtEnergia(obs)}`;
}

function Campos({ children }: { children: ReactNode }) {
  return <dl className="campos">{children}</dl>;
}

function Campo({ rotulo, valor, origem, nota }: { rotulo: string; valor: string | null; origem: DataOrigin | null; nota?: string }) {
  return (
    <div className="campo">
      <dt>{rotulo}</dt>
      <dd>
        <span className={valor == null ? "ausente" : ""}>{valor ?? "não informado na base"}</span>
        <ProvenanceBadge origin={valor == null ? null : origem} />
        {nota && <div className="campo-nota">{nota}</div>}
      </dd>
    </div>
  );
}

/** Curva do período: horária para até 31 dias, diária acima disso. */
function GraficoPeriodo({
  state, index, period, horario, erro,
}: { state: ShadowState; index: number; period: Period; horario: HourlyEnergyFile | null; erro: string | null }) {
  const ef = state.energyFile!;
  const dias = periodDays(period);
  const horarioOk = dias <= 31;
  const dados = useMemo(() => {
    if (horarioOk) {
      if (!horario) return null;
      const a = period.start * 24;
      const b = (period.end + 1) * 24;
      const series: Series[] = [{ label: "Real (kWh/h)", color: COR_REAL, values: horario.kwh.slice(a, b) }];
      if (horario.previsto) series.push({ label: "Previsto (kWh/h)", color: COR_PREV, values: horario.previsto.slice(a, b), dashed: true });
      return {
        series,
        x: (i: number) => {
          const d = dayToDate(ef.inicio, period.start + Math.floor(i / 24));
          return dias <= 1 ? `${String(i % 24).padStart(2, "0")}h` : `${fmtDia(d).slice(0, 6)} ${String(i % 24).padStart(2, "0")}h`;
        },
      };
    }
    const series: Series[] = [
      { label: "Real (kWh/dia)", color: COR_REAL, values: dailyComparable(ef.kwh[index], ef.horas[index]).slice(period.start, period.end + 1) },
    ];
    if (ef.previsao) {
      series.push({ label: "Previsto (kWh/dia)", color: COR_PREV, values: ef.previsao.kwh[index].slice(period.start, period.end + 1), dashed: true });
    }
    return { series, x: (i: number) => fmtDia(dayToDate(ef.inicio, period.start + i)) };
  }, [horarioOk, horario, period, index, ef, dias]);

  if (horarioOk && erro) return <div className="aviso">Falha ao carregar a série horária: {erro}</div>;
  if (!dados) return <div className="grafico-vazio">Carregando série horária...</div>;
  return (
    <>
      <LineChart series={dados.series} xLabel={dados.x} formatValue={(v) => (v == null ? "sem leitura" : fmtNum(v, 1))} />
      {!ef.previsao && <div className="campo-nota">Série prevista vazia: sem previsão importada.</div>}
      {!horarioOk && <div className="campo-nota">Dias completos: soma das 24 leituras. Dias com 12 a 23 horas lidas: extrapolados pela média horária (estimado). Menos de 12 horas: lacuna.</div>}
    </>
  );
}

function Historico({
  state, index, period, horario, building, onPickPeriod,
}: {
  state: ShadowState; index: number; period: Period; horario: HourlyEnergyFile | null; building: Building;
  onPickPeriod: (g: "mes", start: number) => void;
}) {
  const ef = state.energyFile!;
  const energy = state.energy!;
  const meses = useMemo(() => buildPeriods(ef.inicio, ef.dias, "mes"), [ef]);
  const barras = meses.map((m) => {
    const c = consumption(energy.index, index, m);
    return {
      label: fmtMesCurto(dayToDate(ef.inicio, m.start)),
      value: c.kwh,
      estimated: c.origin === "estimated",
      active: m.start <= period.end && m.end >= period.start && period.granularity !== "total",
    };
  });
  const tudo = consumption(energy.index, index, { start: 0, end: ef.dias - 1 });
  const r = building.record;
  return (
    <>
      <h3>Consumo mensal</h3>
      <BarChart bars={barras} formatValue={fmtEnergia} onClick={(i) => onPickPeriod("mes", meses[i].start)} />
      <div className="campo-nota">Clique num mês para selecioná-lo como período.</div>
      <h3>Consumo diário, 2016 e 2017</h3>
      <LineChart
        series={[{ label: "Real (kWh/dia)", color: COR_REAL, values: dailyComparable(ef.kwh[index], ef.horas[index]) }]}
        xLabel={(i) => fmtDia(dayToDate(ef.inicio, i))}
        formatValue={(v) => (v == null ? "sem leitura" : `${fmtNum(v, 0)} kWh`)}
        highlight={period.granularity === "total" ? null : period}
      />
      <div className="campo-nota">Dias com 12 a 23 horas lidas são extrapolados pela média horária; com menos de 12, ficam como lacuna.</div>
      <Campos>
        <Campo rotulo="Consumo 2016 e 2017" valor={fmtEnergia(tudo.kwh)} origem={tudo.origin} nota={notaCobertura(tudo.coverage, tudo.observedKwh)} />
        <Campo rotulo="Mediana horária 2016" valor={r.medianaKwh["2016"] != null ? `${fmtNum(r.medianaKwh["2016"], 1)} kWh/h` : null} origem="observed" />
        <Campo rotulo="Mediana horária 2017" valor={r.medianaKwh["2017"] != null ? `${fmtNum(r.medianaKwh["2017"], 1)} kWh/h` : null} origem="observed" />
        <Campo rotulo="Preenchimento 2016" valor={r.preenchimento["2016"] != null ? fmtPct(r.preenchimento["2016"] * 100, 2) : null} origem="observed" />
        <Campo rotulo="Preenchimento 2017" valor={r.preenchimento["2017"] != null ? fmtPct(r.preenchimento["2017"] * 100, 2) : null} origem="observed" />
        <Campo
          rotulo="Série horária"
          valor={horario ? `${fmtNum(horario.kwh.filter((v) => v != null).length)} de ${fmtNum(horario.horas)} horas com leitura` : "carregando"}
          origem="observed"
        />
      </Campos>
    </>
  );
}

function Construtivo({ b }: { b: Building }) {
  const r = b.record;
  const g = b.geometry;
  return (
    <Campos>
      <Campo rotulo="Área construída" valor={`${fmtNum(r.area)} m²`} origem="observed" />
      <Campo rotulo="Andares" valor={fmtNum(g.floors)} origem={b.origin.floors} nota={g.estimatedFloors ? "Sem numberoffloors na base: estimado por uso e área" : undefined} />
      <Campo rotulo="Altura" valor={`${fmtNum(g.height, 1)} m`} origem="estimated" nota={b.heightRule} />
      <Campo rotulo="Footprint (área / andares)" valor={`${fmtNum(g.footprint)} m²`} origem="estimated" />
      <Campo rotulo="Dimensões do bloco" valor={`${fmtNum(g.width, 1)} x ${fmtNum(g.depth, 1)} m`} origem="estimated" nota="Proporção típica da categoria" />
      <Campo rotulo="Posição no campus" valor="layout procedural" origem="synthetic" nota="O BDG2 não tem coordenadas por prédio" />
      <Campo rotulo="Ano de construção" valor={r.anoConstrucao != null ? String(r.anoConstrucao) : null} origem="observed" />
      <Campo rotulo="Ocupantes" valor={r.ocupantes != null ? fmtNum(r.ocupantes) : null} origem="observed" />
      <Campo rotulo="Setor" valor={r.setor} origem="observed" />
      <Campo rotulo="Subsetor" valor={r.subsetor} origem="observed" />
      <Campo rotulo="Rating" valor={r.rating} origem="observed" />
      <Campo rotulo="Energy Star" valor={r.energyStar != null ? fmtNum(r.energyStar) : null} origem="observed" />
      <Campo rotulo="EUI cadastrado" valor={r.euiCadastro != null ? fmtNum(r.euiCadastro, 1) : null} origem="observed" nota={r.euiCadastro != null ? "Valor da base, unidade original do BDG2" : undefined} />
      <Campo rotulo="LEED" valor={r.leed} origem="observed" />
    </Campos>
  );
}

function Sistemas({ b }: { b: Building }) {
  const r = b.record;
  const med: [keyof typeof r.medidores, string][] = [
    ["chilledwater", "Água gelada"],
    ["steam", "Vapor"],
    ["hotwater", "Água quente"],
    ["gas", "Gás"],
    ["water", "Água"],
    ["irrigation", "Irrigação"],
    ["solar", "Solar"],
  ];
  return (
    <>
      <Campos>
        <Campo rotulo="Tipo de aquecimento" valor={r.aquecimento} origem="observed" />
        <Campo rotulo="Eletricidade" valor="medidor presente (dados usados na cena)" origem="observed" />
      </Campos>
      <h3>Outros medidores</h3>
      <ul className="medidores">
        {med.map(([k, label]) => (
          <li key={k} className={r.medidores[k] ? "tem" : ""}>
            <span className="medidor-marca" />
            {label}: {r.medidores[k] ? "tem medidor" : "sem medidor na base"}
          </li>
        ))}
      </ul>
      <div className="campo-nota">
        A base só indica se o medidor existe. As séries desses medidores não estão carregadas neste protótipo.
      </div>
    </>
  );
}
