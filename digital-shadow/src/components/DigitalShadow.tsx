import { useEffect, useState, useSyncExternalStore } from "react";
import { DigitalShadowController } from "../controller/DigitalShadowController.ts";
import { BuildingPanel } from "./BuildingPanel.tsx";
import { SceneCanvas } from "./SceneCanvas.tsx";
import { SceneControls } from "./SceneControls.tsx";
import { SiteHeader } from "./SiteHeader.tsx";
import { SitePanel } from "./SitePanel.tsx";

export function DigitalShadow() {
  const [ctl] = useState(() => new DigitalShadowController());
  const state = useSyncExternalStore(ctl.subscribe, ctl.getState);

  useEffect(() => {
    ctl.init();
    return () => ctl.stop();
  }, [ctl]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") ctl.select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ctl]);

  const period = state.periods[state.periodIndex];
  const b = state.model && state.selected != null ? state.model.buildings[state.selected] : null;

  return (
    <div className="app">
      <SiteHeader state={state} ctl={ctl} />
      <main className="corpo">
        <section className="cena-wrap">
          <SceneCanvas ctl={ctl} state={state} />
          <SceneControls ctl={ctl} state={state} />
          {state.status === "carregando" && <div className="cena-status">Carregando {state.siteId ?? ""}...</div>}
          {state.status === "erro" && <div className="cena-status erro">{state.error}</div>}
        </section>
        {state.status === "pronto" && period && (
          b ? (
            <BuildingPanel
              key={b.id}
              state={state}
              building={b}
              index={state.selected!}
              period={period}
              onClose={() => ctl.select(null)}
              onPickPeriod={(g, start) => {
                ctl.setGranularity(g);
                const i = ctl.getState().periods.findIndex((p) => p.start === start);
                if (i >= 0) ctl.setPeriodIndex(i);
              }}
            />
          ) : (
            <SitePanel state={state} onSelect={(i) => ctl.select(i)} />
          )
        )}
      </main>
    </div>
  );
}
