import { useEffect, useRef } from "react";
import type { DigitalShadowController, ShadowState } from "../controller/DigitalShadowController.ts";
import { metricDef } from "../domain/EnergyMetrics.ts";
import { rotuloUso } from "../domain/Site.ts";
import { fmtMetric } from "../utils/format.ts";

/** Contêiner do canvas WebGL. A cena em si é dona do SceneManager, via controller. */
export function SceneCanvas({ ctl, state }: { ctl: DigitalShadowController; state: ShadowState }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    ctl.attach(ref.current);
    return () => ctl.detach();
  }, [ctl]);

  const h = state.hover;
  const b = h && state.model ? state.model.buildings[h.index] : null;
  const def = metricDef(state.metric);
  const v = h ? state.evaluation?.result.values[h.index] ?? null : null;
  const rect = ref.current?.getBoundingClientRect();

  return (
    <div className="cena" ref={ref}>
      {b && h && rect && (
        <div className="dica" style={{ left: h.x - rect.left + 14, top: h.y - rect.top + 14 }}>
          <strong>{b.name}</strong>
          <span>{rotuloUso(b.usage)}</span>
          <span>
            {def.label}: {fmtMetric(v, def.unit)}
          </span>
        </div>
      )}
    </div>
  );
}
