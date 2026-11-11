"""FedAvg escrito à mão (McMahan et al., 2017).

Em cada rodada:
  1. o servidor envia os pesos globais w para todos os clientes;
  2. cada cliente k copia w, treina E épocas nos seus dados e obtém w_k;
  3. o cliente devolve a ATUALIZAÇÃO de pesos delta_k = w_k - w (não um gradiente bruto:
     delta_k acumula vários passos de otimização locais);
  4. o servidor faz w <- w + sum_k (n_k / n) * delta_k, que é a média ponderada dos w_k.
"""
import copy

import torch

from .config import AMOSTRA_PERDA_LOCAL, EPOCAS_LOCAIS, RODADAS, SEED
from .modelo import mse, novo_modelo, treinar


def _vetor(modelo):
    return torch.cat([p.detach().flatten() for p in modelo.parameters()])


def rodar(dados, n_entradas, log=print):
    """dados: {site: {"Xtr","ytr","Xva","yva"}}. Retorna modelo global e log por rodada."""
    g = torch.Generator().manual_seed(SEED)
    global_ = novo_modelo(n_entradas, SEED)
    sites = list(dados)
    n_k = {s: len(dados[s]["Xtr"]) for s in sites}
    n_total = sum(n_k.values())
    peso = {s: n_k[s] / n_total for s in sites}

    # amostra fixa de treino por cliente para medir perda local antes/depois (barato e comparável)
    amostra = {}
    for s in sites:
        idx = torch.randperm(n_k[s], generator=g)[:AMOSTRA_PERDA_LOCAL]
        amostra[s] = (dados[s]["Xtr"][idx], dados[s]["ytr"][idx])

    def perda_val_global(m):
        tot = sum(mse(m, dados[s]["Xva"], dados[s]["yva"]) * len(dados[s]["Xva"]) for s in sites)
        return tot / sum(len(dados[s]["Xva"]) for s in sites)

    historico = [{"rodada": 0, "perda_val_global": perda_val_global(global_), "clientes": {}}]
    log(f"  rodada  0  perda val global {historico[0]['perda_val_global']:.4f}")
    for r in range(1, RODADAS + 1):
        w_global = _vetor(global_)
        estados, info = {}, {}
        for s in sites:
            local = copy.deepcopy(global_)                       # 1. recebe w
            antes = mse(local, *amostra[s])
            treinar(local, dados[s]["Xtr"], dados[s]["ytr"], EPOCAS_LOCAIS, g)  # 2. E épocas
            depois = mse(local, *amostra[s])
            delta = _vetor(local) - w_global                     # 3. delta_k
            estados[s] = local.state_dict()
            info[s] = {
                "n_amostras": n_k[s],
                "peso_media": peso[s],
                "perda_local_antes": antes,
                "perda_local_depois": depois,
                "norma_delta": float(delta.norm()),
                "perda_val_local": mse(local, dados[s]["Xva"], dados[s]["yva"]),
            }
        # 4. agregação ponderada
        novo = {k: sum(peso[s] * estados[s][k] for s in sites) for k in estados[sites[0]]}
        global_.load_state_dict(novo)
        pv = perda_val_global(global_)
        historico.append({"rodada": r, "perda_val_global": pv, "clientes": info})
        log(f"  rodada {r:2d}  perda val global {pv:.4f}  "
            + "  ".join(f"{s}:|dw|={info[s]['norma_delta']:.3f}" for s in sites))
    return global_, historico
