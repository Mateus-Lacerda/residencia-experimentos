import type { DataOrigin } from "../domain/Building.ts";
import { ROTULO_ORIGEM } from "../domain/Building.ts";

const DICA: Record<DataOrigin, string> = {
  observed: "Presente na base BDG2",
  estimated: "Inferido a partir de outros dados (regra no README)",
  synthetic: "Criado para completar o cenário; não corresponde à realidade",
};

export function ProvenanceBadge({ origin }: { origin: DataOrigin | null }) {
  if (!origin) return <span className="badge badge-ausente" title="Não existe na base">sem dado</span>;
  return (
    <span className={`badge badge-${origin}`} title={DICA[origin]}>
      {ROTULO_ORIGEM[origin]}
    </span>
  );
}
