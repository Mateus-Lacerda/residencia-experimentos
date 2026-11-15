import type { DigitalShadowController, ShadowState } from "../controller/DigitalShadowController.ts";
import { fmtNum } from "../utils/format.ts";
import { ProvenanceBadge } from "./ProvenanceBadge.tsx";

export function SceneControls({ ctl, state }: { ctl: DigitalShadowController; state: ShadowState }) {
  const s = state.stats;
  return (
    <>
      <div className="cena-controles">
        <button onClick={() => ctl.resetCamera()} title="Retorna à visão isométrica inicial">Resetar visão</button>
        <label className="check">
          <input type="checkbox" checked={state.showTrees} onChange={(e) => ctl.setTrees(e.target.checked)} />
          Árvores
        </label>
      </div>
      <div className="cena-aviso">
        <ProvenanceBadge origin="synthetic" /> Posições, terreno, vias, calçadas, árvores e estacionamentos são sintéticos:
        o BDG2 não tem a planta dos campi. Arrastar gira, scroll aproxima, botão direito desloca.
      </div>
      {s && (
        <div className="cena-stats" title="Medidas do próprio navegador">
          cena gerada em {fmtNum(s.buildMs, 0)} ms · carga total {fmtNum(state.loadMs, 0)} ms · {fmtNum(s.drawCalls)} draw calls ·{" "}
          {fmtNum(s.instances)} peças de prédio · quadro {fmtNum(s.lastFrameMs, 1)} ms
        </div>
      )}
    </>
  );
}
