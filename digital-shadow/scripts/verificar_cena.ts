/**
 * Verificação do gerador e das métricas, rodando o mesmo código TypeScript do navegador.
 * Uso: node scripts/verificar_cena.ts   (Node 26 executa TypeScript por remoção de tipos)
 *
 * Checa, para os 11 sites:
 * - número de prédios gerados = número de edificações do site;
 * - nenhum par de prédios se sobrepõe (caixas envolventes rotacionadas);
 * - layout determinístico (duas gerações produzem a mesma cena);
 * - métricas: lacuna nunca vira zero (casos sintéticos e dados reais).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { generateSite } from "../src/generators/SiteGenerator.ts";
import { buildEnergyIndex, computeMetric, consumption, siteSummary } from "../src/domain/EnergyMetrics.ts";
import type { DailyEnergyFile, SiteBuildingsFile, SitesIndex } from "../src/domain/Site.ts";

const DADOS = join(import.meta.dirname, "..", "public", "data");
const ler = <T>(p: string): T => JSON.parse(readFileSync(join(DADOS, p), "utf8")) as T;
const falhas: string[] = [];
const checar = (cond: boolean, msg: string) => {
  if (!cond) falhas.push(msg);
};

// --- 1. casos sintéticos de lacuna -----------------------------------------------------
{
  const dias = 10;
  const base: DailyEnergyFile = {
    site: "Teste",
    inicio: "2016-01-01",
    dias,
    unidade: "kWh",
    edificacoes: ["a", "b", "c"],
    // a: completo; b: sem nenhuma leitura; c: metade dos dias sem leitura
    kwh: [Array(dias).fill(240), Array(dias).fill(null), Array.from({ length: dias }, (_, i) => (i % 2 ? null : 240))],
    horas: [Array(dias).fill(24), Array(dias).fill(0), Array.from({ length: dias }, (_, i) => (i % 2 ? 0 : 24))],
    previsao: null,
    clima: null,
  };
  const ix = buildEnergyIndex(base);
  const p = { start: 0, end: dias - 1 };
  const a = consumption(ix, 0, p);
  const b = consumption(ix, 1, p);
  const c = consumption(ix, 2, p);
  checar(a.kwh === 2400 && a.origin === "observed", "sintético: prédio completo deveria somar 2400 observado");
  checar(b.kwh === null && b.origin === null, "sintético: prédio sem leitura deveria ser null, não zero");
  checar(c.kwh === 2400 && c.origin === "estimated", `sintético: 50% de cobertura deveria estimar 2400 (deu ${c.kwh})`);
  checar(c.observedKwh === 1200, "sintético: lido de c deveria ser 1200");
  const eui = computeMetric(ix, [10, 10, 10], "eui", p);
  checar(eui.values[1] === null, "sintético: EUI de prédio sem leitura deveria ser null");
  const s = siteSummary(ix, [10, 10, 10], p);
  checar(s.comDado === 2 && s.semDado === 1, "sintético: resumo deveria ter 2 com dado e 1 sem");
  checar(Math.abs(s.coverage - (10 * 24 + 5 * 24) / (3 * 10 * 24)) < 1e-9, "sintético: cobertura do site errada");
  // 40% de cobertura: abaixo do mínimo, vira sem dado
  const d40 = { ...base, edificacoes: ["d"], kwh: [Array.from({ length: dias }, (_, i) => (i < 4 ? 240 : null))], horas: [Array.from({ length: dias }, (_, i) => (i < 4 ? 24 : 0))] };
  const c40 = consumption(buildEnergyIndex(d40), 0, p);
  checar(c40.kwh === null, "sintético: 40% de cobertura deveria ser sem dado");
  const erro = computeMetric(ix, [10, 10, 10], "erro", p);
  checar(erro.unavailable != null && erro.values.every((v) => v === null), "sintético: erro sem previsões deveria estar indisponível");

  // com previsões: a (completo) previsto 10% acima; b sem leitura real -> erro null mesmo com previsão
  const comPrev: DailyEnergyFile = {
    ...base,
    previsao: {
      kwh: [Array(dias).fill(264), Array(dias).fill(100), Array(dias).fill(null)],
      horas: [Array(dias).fill(24), Array(dias).fill(24), Array(dias).fill(0)],
      pareadoPrevisto: [Array(dias).fill(264), Array(dias).fill(null), Array(dias).fill(null)],
      pareadoReal: [Array(dias).fill(240), Array(dias).fill(null), Array(dias).fill(null)],
      pareadoHoras: [Array(dias).fill(24), Array(dias).fill(0), Array(dias).fill(0)],
    },
  };
  const e2 = computeMetric(buildEnergyIndex(comPrev), [10, 10, 10], "erro", p);
  checar(e2.unavailable === null, "sintético: com previsões o erro deveria estar disponível");
  checar(Math.abs((e2.values[0] ?? NaN) - 10) < 1e-9, `sintético: erro deveria ser +10% (deu ${e2.values[0]})`);
  checar(e2.values[1] === null && e2.values[2] === null, "sintético: erro sem horas pareadas deveria ser null");
}

// --- 2. sites reais --------------------------------------------------------------------
const indice = ler<SitesIndex>("sites.json");
let total = 0;
console.log("site      prédios  sobreposições  determinístico  terreno (m)     zero-por-lacuna");
for (const s of indice.sites) {
  const meta = ler<SiteBuildingsFile>(`sites/${s.id}/edificacoes.json`);
  const en = ler<DailyEnergyFile>(`sites/${s.id}/energia_diaria.json`);
  const ordem = new Map(en.edificacoes.map((id, i) => [id, i]));
  const recs = [...meta.edificacoes].sort((a, b) => ordem.get(a.id)! - ordem.get(b.id)!);
  const m1 = generateSite(s.id, recs);
  const m2 = generateSite(s.id, JSON.parse(JSON.stringify(recs)));
  total += m1.buildings.length;
  checar(m1.buildings.length === s.edificacoes, `${s.id}: ${m1.buildings.length} prédios gerados, esperado ${s.edificacoes}`);

  const caixas = m1.buildings.map((b) => {
    const rot = Math.abs(Math.sin(b.position.rotation)) > 0.5;
    const w = rot ? b.geometry.depth : b.geometry.width;
    const d = rot ? b.geometry.width : b.geometry.depth;
    return { x: b.position.x - w / 2, z: b.position.z - d / 2, w, d };
  });
  let sobre = 0;
  for (let i = 0; i < caixas.length; i++) {
    for (let j = i + 1; j < caixas.length; j++) {
      const a = caixas[i];
      const b = caixas[j];
      if (a.x < b.x + b.w - 1e-6 && b.x < a.x + a.w - 1e-6 && a.z < b.z + b.d - 1e-6 && b.z < a.z + a.d - 1e-6) sobre++;
    }
  }
  checar(sobre === 0, `${s.id}: ${sobre} pares de prédios sobrepostos`);
  // as peças dos templates não podem sair da caixa do prédio
  for (const b of m1.buildings) {
    for (const p of b.geometry.parts) {
      const ok = Math.abs(p.dx) + p.width / 2 <= b.geometry.width / 2 + 1e-6 && Math.abs(p.dz) + p.depth / 2 <= b.geometry.depth / 2 + 1e-6;
      checar(ok, `${b.id}: peça do template fora do footprint`);
    }
  }
  const det = JSON.stringify(m1.buildings.map((b) => [b.position, b.geometry])) === JSON.stringify(m2.buildings.map((b) => [b.position, b.geometry]))
    && JSON.stringify(m1.trees) === JSON.stringify(m2.trees) && JSON.stringify(m1.roads) === JSON.stringify(m2.roads);
  checar(det, `${s.id}: layout não determinístico`);

  // métricas com dados reais: prédio sem nenhuma leitura no período nunca recebe zero
  const ix = buildEnergyIndex(en);
  const areas = recs.map((r) => r.area);
  let violacoes = 0;
  for (const p of [{ start: 0, end: 365 }, { start: 366, end: 730 }, { start: 31, end: 59 }, { start: 400, end: 400 }]) {
    const r = computeMetric(ix, areas, "consumo", p);
    for (let b = 0; b < ix.n; b++) {
      const c = consumption(ix, b, p);
      if (c.observedHours === 0 && r.values[b] !== null) violacoes++;
      if (c.coverage < 0.5 && r.values[b] !== null) violacoes++;
      if (r.values[b] === 0 && c.observedKwh !== 0) violacoes++;
    }
  }
  checar(violacoes === 0, `${s.id}: ${violacoes} casos de lacuna tratada como valor`);
  const t = m1.layout.terrain;
  console.log(
    `${s.id.padEnd(9)} ${String(m1.buildings.length).padStart(7)}  ${String(sobre).padStart(13)}  ${String(det ? "sim" : "NAO").padStart(14)}  ${`${Math.round(t.w)} x ${Math.round(t.d)}`.padEnd(15)} ${violacoes}`,
  );
}
checar(total === indice.totalEdificacoes, `total gerado ${total} != ${indice.totalEdificacoes}`);

if (falhas.length) {
  console.log(`\n${falhas.length} falha(s):`);
  for (const f of falhas.slice(0, 40)) console.log("  -", f);
  process.exit(1);
}
console.log(`\nok: ${total} prédios em ${indice.sites.length} sites; casos sintéticos de lacuna passaram`);
