/**
 * Digital Shadow Controller: estado da aplicação (site, período, métrica, seleção) e ponte
 * entre o dashboard React e os managers da cena. O React só lê o snapshot e chama ações.
 *
 * Fluxo de energia: período/métrica -> EnergyManager (valores + domínio) ->
 * SceneManager.applyEnergy (EnergyRenderer recolore as instâncias). A geometria só é
 * gerada em loadSite.
 */

import type { Building } from "../domain/Building.ts";
import type { DailyEnergyFile, SiteInfo, SitesIndex } from "../domain/Site.ts";
import { carregarEdificacoes, carregarEnergiaDiaria, carregarIndice } from "../domain/Site.ts";
import { buildPeriods, type Granularity, type Period } from "../domain/Period.ts";
import { siteSummary, type MetricId, type SiteSummary } from "../domain/EnergyMetrics.ts";
import { EnergyManager, type EnergyState } from "../engine/EnergyManager.ts";
import { SceneManager, type SceneStats } from "../engine/SceneManager.ts";
import { generateSite, type SiteModel } from "../generators/SiteGenerator.ts";
import type { ScaleMode } from "../utils/normalization.ts";

export interface HoverInfo {
  index: number;
  x: number;
  y: number;
}

export interface ShadowState {
  index: SitesIndex | null;
  siteId: string | null;
  status: "carregando" | "pronto" | "erro";
  error: string | null;
  site: SiteInfo | null;
  model: SiteModel | null;
  energyFile: DailyEnergyFile | null;
  energy: EnergyManager | null;
  granularity: Granularity;
  periods: Period[];
  periodIndex: number;
  metric: MetricId;
  scale: ScaleMode;
  selected: number | null;
  hover: HoverInfo | null;
  evaluation: EnergyState | null;
  summary: SiteSummary | null;
  playing: boolean;
  showTrees: boolean;
  stats: SceneStats | null;
  loadMs: number;
}

const SITE_INICIAL = "Lamb";

export class DigitalShadowController {
  private state: ShadowState = {
    index: null,
    siteId: null,
    status: "carregando",
    error: null,
    site: null,
    model: null,
    energyFile: null,
    energy: null,
    granularity: "ano",
    periods: [],
    periodIndex: 0,
    metric: "eui",
    scale: "quantil",
    selected: null,
    hover: null,
    evaluation: null,
    summary: null,
    playing: false,
    showTrees: true,
    stats: null,
    loadMs: 0,
  };
  private listeners = new Set<() => void>();
  private scene: SceneManager | null = null;
  private timer = 0;
  private loadToken = 0;

  getState = () => this.state;

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  private set(patch: Partial<ShadowState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => l());
  }

  get period(): Period | null {
    return this.state.periods[this.state.periodIndex] ?? null;
  }

  get selectedBuilding(): Building | null {
    const { model, selected } = this.state;
    return model && selected != null ? model.buildings[selected] : null;
  }

  async init() {
    try {
      const index = await carregarIndice();
      this.set({ index });
      const inicial = index.sites.some((s) => s.id === SITE_INICIAL) ? SITE_INICIAL : index.sites[0]?.id;
      if (inicial) await this.loadSite(inicial);
    } catch (e) {
      this.set({
        status: "erro",
        error: `${(e as Error).message}. Gere os dados com "npm run dados" (ver README).`,
      });
    }
  }

  attach(container: HTMLElement) {
    this.scene = new SceneManager(container, {
      onHover: (i, x, y) => {
        this.scene?.setHover(i);
        this.set({ hover: i == null ? null : { index: i, x, y } });
      },
      onSelect: (i) => this.select(i),
    });
    this.scene.onStats = (stats) => this.set({ stats });
    if (this.state.model) {
      this.scene.loadSite(this.state.model);
      this.scene.setTreesVisible(this.state.showTrees);
      this.refreshEnergy();
    }
  }

  detach() {
    this.scene?.dispose();
    this.scene = null;
  }

  async loadSite(siteId: string) {
    const token = ++this.loadToken;
    this.stop();
    this.set({ status: "carregando", siteId, selected: null, hover: null, error: null });
    const t0 = performance.now();
    try {
      const [edif, energia] = await Promise.all([carregarEdificacoes(siteId), carregarEnergiaDiaria(siteId)]);
      if (token !== this.loadToken) return;
      // a ordem das edificações em energia_diaria.json é a mesma de edificacoes.json
      const ordem = new Map(energia.edificacoes.map((id, i) => [id, i]));
      const records = [...edif.edificacoes].sort((a, b) => ordem.get(a.id)! - ordem.get(b.id)!);
      if (records.length !== energia.edificacoes.length || records.some((r, i) => r.id !== energia.edificacoes[i])) {
        throw new Error(`Arquivos de ${siteId} inconsistentes: edificações diferentes em metadados e energia`);
      }
      const model = generateSite(siteId, records);
      const energy = new EnergyManager(energia, records.map((r) => r.area));
      const periods = buildPeriods(energia.inicio, energia.dias, this.state.granularity);
      this.set({
        site: edif.site,
        model,
        energyFile: energia,
        energy,
        periods,
        periodIndex: Math.min(this.state.periodIndex, periods.length - 1),
        metric: this.state.metric === "erro" && !energy.hasPredictions ? "eui" : this.state.metric,
        status: "pronto",
      });
      this.scene?.loadSite(model);
      this.scene?.setTreesVisible(this.state.showTrees);
      this.refreshEnergy();
      this.set({ loadMs: performance.now() - t0 });
    } catch (e) {
      if (token !== this.loadToken) return;
      this.set({ status: "erro", error: (e as Error).message });
    }
  }

  private refreshEnergy() {
    const { energy, metric, scale, selected } = this.state;
    const p = this.period;
    if (!energy || !p) return;
    const evaluation = energy.evaluate(metric, p, scale);
    const summary = siteSummary(energy.index, energy.areas, p);
    this.set({ evaluation, summary });
    this.scene?.applyEnergy(evaluation.result, evaluation.domain, selected);
  }

  setGranularity(g: Granularity) {
    const { energyFile } = this.state;
    if (!energyFile) return;
    const atual = this.period;
    const periods = buildPeriods(energyFile.inicio, energyFile.dias, g);
    let idx = atual ? periods.findIndex((p) => p.start <= atual.start && p.end >= atual.start) : 0;
    if (idx < 0) idx = 0;
    this.set({ granularity: g, periods, periodIndex: idx });
    if (g === "total") this.stop();
    this.refreshEnergy();
  }

  setPeriodIndex(i: number) {
    const n = this.state.periods.length;
    if (n === 0) return;
    this.set({ periodIndex: Math.max(0, Math.min(n - 1, i)) });
    this.refreshEnergy();
  }

  setMetric(metric: MetricId) {
    this.set({ metric });
    this.refreshEnergy();
  }

  setScale(scale: ScaleMode) {
    this.set({ scale });
    this.refreshEnergy();
  }

  select(i: number | null) {
    this.set({ selected: i });
    this.refreshEnergy();
  }

  setTrees(v: boolean) {
    this.set({ showTrees: v });
    this.scene?.setTreesVisible(v);
  }

  resetCamera() {
    this.scene?.resetCamera();
  }

  togglePlay() {
    if (this.state.playing) return this.stop();
    if (this.state.periods.length < 2) return;
    this.set({ playing: true });
    this.timer = window.setInterval(() => {
      const n = this.state.periods.length;
      this.setPeriodIndex((this.state.periodIndex + 1) % n);
    }, 900);
  }

  stop() {
    window.clearInterval(this.timer);
    this.timer = 0;
    if (this.state.playing) this.set({ playing: false });
  }

  dispose() {
    this.stop();
    this.detach();
  }
}
