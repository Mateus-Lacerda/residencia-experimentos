"""Heterogeneidade entre os clientes (sites), em três dos tipos de non-IID de Kairouz et al. (2021, seção 3.1).

uv run python -m bdg2_fl.heterogeneidade

- Quantity skew: quanto dado cada site tem e quanto pesa na média do FedAvg.
- Label distribution skew, P_i(y): distribuição do consumo de eletricidade de cada site.
- Feature distribution skew, P_i(x): distribuição das entradas externas (clima) e dos medidores opcionais.

Tudo sobre o treino (2016), que é o que cada cliente usa para treinar. Cada distribuição é vista em
duas escalas: a física (kWh, °C), e a normalizada que o modelo recebe (z-score por edificação no
consumo, por site no clima). A normalização por cliente tira média e escala; o que sobra de
diferença na escala normalizada é de forma (assimetria, cauda, bimodalidade).

Fica de fora das features: o calendário (seno/cosseno de hora e dia da semana), que é igual em todos
os sites, e os lags de eletricidade, que são o próprio y defasado e já aparecem no label skew.

Distância entre duas distribuições: Wasserstein-1, calculada pelos quantis (média de |Q_a(p) - Q_b(p)|
em 999 quantis), na unidade da própria variável.

Saída em out/heterogeneidade/: CSVs com as tabelas e PNGs com os gráficos.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from .config import MEDIDORES_OPCIONAIS, RAIZ, RAW
from .dados import construir
from .graficos import MUDO, SEQ_AZUL, SERIES, TINTA, TINTA_2, aplicar_estilo

SAIDA = RAIZ / "out" / "heterogeneidade"
P = np.linspace(0.001, 0.999, 999)
NOME_MEDIDOR = {"chilledwater": "água gelada", "steam": "vapor", "hotwater": "água quente", "gas": "gás"}


def _virgula(casas):
    return FuncFormatter(lambda v, _: f"{v:.{casas}f}".replace(".", ","))


def w1(a, b):
    """Wasserstein-1 entre duas amostras 1-D, pelos quantis."""
    return float(np.mean(np.abs(np.quantile(a, P) - np.quantile(b, P))))


def matriz_w1(amostras):
    sites = list(amostras)
    q = {s: np.quantile(amostras[s], P) for s in sites}
    m = pd.DataFrame(0.0, index=sites, columns=sites)
    for a in sites:
        for b in sites:
            m.loc[a, b] = float(np.mean(np.abs(q[a] - q[b])))
    return m


def contra_resto(amostras):
    """W1 de cada site contra a união dos outros sites."""
    return {s: w1(v, np.concatenate([amostras[o] for o in amostras if o != s])) for s, v in amostras.items()}


def gini(x):
    x = np.sort(np.asarray(x, float))
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


# ---------------------------------------------------------------------------------------------- dados

def clima_bruto(sites):
    """Temperatura do ar e ponto de orvalho em °C, 2016, mesmo tratamento de dados.py (sem o z-score)."""
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    idx = pd.date_range("2016-01-01", "2016-12-31 23:00", freq="h")
    out = {}
    for s in sites:
        w = (clima[clima.site_id == s].set_index("timestamp").reindex(idx)
             [["airTemperature", "dewTemperature"]].interpolate(limit_direction="both"))
        out[s] = w
    return out


# ------------------------------------------------------------------------------------------- gráficos

def faixas(ax, amostras, ordem, unidade, casas=1, log=False):
    """Uma linha por site: p5–p95 fino, p25–p75 grosso, mediana em ponto."""
    for i, s in enumerate(ordem):
        p5, p25, p50, p75, p95 = np.quantile(amostras[s], [0.05, 0.25, 0.5, 0.75, 0.95])
        ax.plot([p5, p95], [i, i], color=SERIES[0], lw=1.5, solid_capstyle="round")
        ax.plot([p25, p75], [i, i], color=SERIES[0], lw=6, solid_capstyle="round")
        ax.plot(p50, i, "o", ms=6, color="white", mec=SERIES[0], mew=1.8, zorder=3)
    ax.set_yticks(range(len(ordem)), ordem)
    ax.set_ylim(-0.6, len(ordem) - 0.4)
    ax.invert_yaxis()
    ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelcolor=TINTA)
    ax.set_xlabel(unidade)
    if log:
        ax.set_xscale("log")
    else:
        ax.xaxis.set_major_formatter(_virgula(casas))


def mapa(ax, m, titulo, casas):
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", ["#f4f8fd"] + SEQ_AZUL)
    v = m.values
    im = ax.imshow(v, cmap=cmap, vmin=0)
    n = len(m)
    ax.set_xticks(range(n), m.columns, rotation=60, ha="right")
    ax.set_yticks(range(n), m.index)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0, labelcolor=TINTA_2)
    lim = v.max() * 0.55
    for i in range(n):
        for j in range(n):
            if i != j:
                ax.text(j, i, f"{v[i, j]:.{casas}f}".replace(".", ","), ha="center", va="center", fontsize=6.5,
                        color="white" if v[i, j] > lim else TINTA)
    ax.set_title(titulo)
    return im


def salvar(fig, nome):
    fig.tight_layout()
    fig.savefig(SAIDA / nome, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(SAIDA / nome)


# ------------------------------------------------------------------------------------------- análises

def quantidade(clientes):
    linhas = []
    for s, c in clientes.items():
        tr = c["treino"]
        linhas.append({"site": s, "edificacoes": len(c["edificacoes"]), "amostras_treino": len(tr),
                       "amostras_teste": len(c["val"]), "kwh_total_2016": tr["y_kwh"].sum()})
    q = pd.DataFrame(linhas).set_index("site").sort_values("amostras_treino", ascending=False)
    q["peso_fedavg"] = q["amostras_treino"] / q["amostras_treino"].sum()
    q["fracao_kwh"] = q["kwh_total_2016"] / q["kwh_total_2016"].sum()
    q.to_csv(SAIDA / "quantidade.csv")
    resumo = {"gini_amostras": gini(q["amostras_treino"]), "gini_edificacoes": gini(q["edificacoes"]),
              "max_sobre_min_amostras": q["amostras_treino"].max() / q["amostras_treino"].min()}
    pd.Series(resumo).to_csv(SAIDA / "quantidade_resumo.csv", header=["valor"])

    fig, ax = plt.subplots(figsize=(7, 4.2))
    y = np.arange(len(q))
    ax.barh(y, q["peso_fedavg"] * 100, color=SERIES[0], height=0.6)
    ax.axvline(100 / len(q), color=MUDO, ls="--", lw=1.1)
    ax.text(100 / len(q), -0.75, " peso igual (1/11)", color=MUDO, fontsize=8, va="bottom")
    for i, (s, r) in enumerate(q.iterrows()):
        ax.text(r.peso_fedavg * 100 + 0.3, i, f"{r.edificacoes:.0f} edif.", va="center", fontsize=8, color=TINTA_2)
    ax.set_yticks(y, q.index); ax.invert_yaxis()
    ax.set_ylim(len(q) - 0.5, -1.1)
    ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0, labelcolor=TINTA)
    ax.set_xlabel("peso na média do FedAvg (% das amostras de treino)")
    ax.xaxis.set_major_formatter(_virgula(0))
    ax.set_title(f"Quantity skew: Gini das amostras = {resumo['gini_amostras']:.2f}".replace(".", ","))
    salvar(fig, "quantidade.png")
    return q, resumo


def rotulo(clientes, ordem):
    # escala física: consumo médio de cada edificação (o que define o peso dela no RMSE em kWh)
    kwh_edif = {s: clientes[s]["treino"].groupby("edif")["y_kwh"].mean().values for s in ordem}
    yz = {s: clientes[s]["treino"]["y"].values for s in ordem}
    log_kwh = {s: np.log10(clientes[s]["treino"]["y_kwh"].clip(lower=0.1).values) for s in ordem}

    mz, mk = matriz_w1(yz), matriz_w1(log_kwh)
    mz.to_csv(SAIDA / "rotulo_w1_zscore.csv"); mk.to_csv(SAIDA / "rotulo_w1_log10kwh.csv")
    desc = pd.DataFrame({
        "kwh_medio_edif_mediana": {s: np.median(v) for s, v in kwh_edif.items()},
        "kwh_medio_edif_max": {s: v.max() for s, v in kwh_edif.items()},
        "z_assimetria": {s: pd.Series(v).skew() for s, v in yz.items()},
        "z_curtose": {s: pd.Series(v).kurt() for s, v in yz.items()},
        "w1_z_contra_resto": contra_resto(yz),
        "w1_log10kwh_contra_resto": contra_resto(log_kwh),
    })
    desc.to_csv(SAIDA / "rotulo_resumo.csv")

    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)
    faixas(a, kwh_edif, ordem, "consumo médio por edificação em 2016 (kWh/h, escala log)", log=True)
    a.set_title("Escala física: consumo médio das edificações")
    faixas(b, yz, ordem, "consumo normalizado (z-score por edificação)")
    b.set_xlim(-3, 5)
    b.set_title("Escala do modelo: consumo horário em z-score")
    fig.text(0.01, 0.005, "linha fina: p5–p95 · barra: p25–p75 · ponto: mediana", fontsize=8, color=MUDO)
    salvar(fig, "rotulo_distribuicoes.png")

    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 5))
    mapa(a, mk, "W1 do consumo em log10(kWh)", 2)
    mapa(b, mz, "W1 do consumo em z-score", 2)
    salvar(fig, "rotulo_w1.png")
    return desc


def features(clientes, ordem):
    bruto = clima_bruto(ordem)
    temp = {s: bruto[s]["airTemperature"].values for s in ordem}
    orv = {s: bruto[s]["dewTemperature"].values for s in ordem}
    # na escala do modelo: o z-score do clima é por site, então cada série tem média 0 e desvio 1
    temp_z = {s: (v - v.mean()) / v.std() for s, v in temp.items()}

    mt, mo, mtz = matriz_w1(temp), matriz_w1(orv), matriz_w1(temp_z)
    mt.to_csv(SAIDA / "features_w1_temperatura_c.csv"); mo.to_csv(SAIDA / "features_w1_orvalho_c.csv")
    mtz.to_csv(SAIDA / "features_w1_temperatura_z.csv")

    # medidores opcionais: fração das edificações do site em que o medidor entra no modelo
    pres = pd.DataFrame({NOME_MEDIDOR[m]: {s: clientes[s]["treino"].groupby("edif")[f"tem_{m}"].first().mean()
                                           for s in ordem} for m in MEDIDORES_OPCIONAIS})
    pres.to_csv(SAIDA / "features_medidores_presentes.csv")
    desc = pd.DataFrame({
        "temp_media_c": {s: v.mean() for s, v in temp.items()},
        "temp_desvio_c": {s: v.std() for s, v in temp.items()},
        "orvalho_media_c": {s: v.mean() for s, v in orv.items()},
        "w1_temp_c_contra_resto": contra_resto(temp),
        "w1_orvalho_c_contra_resto": contra_resto(orv),
        "w1_temp_z_contra_resto": contra_resto(temp_z),
    }).join(pres)
    desc.to_csv(SAIDA / "features_resumo.csv")

    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)
    faixas(a, temp, ordem, "temperatura do ar em 2016 (°C)", casas=0)
    a.set_title("Escala física: temperatura do ar")
    faixas(b, orv, ordem, "ponto de orvalho em 2016 (°C)", casas=0)
    b.set_title("Escala física: ponto de orvalho")
    fig.text(0.01, 0.005, "linha fina: p5–p95 · barra: p25–p75 · ponto: mediana", fontsize=8, color=MUDO)
    salvar(fig, "features_clima.png")

    fig, axs = plt.subplots(1, 3, figsize=(16, 5.2))
    mapa(axs[0], mt, "W1 da temperatura (°C)", 1)
    mapa(axs[1], mo, "W1 do ponto de orvalho (°C)", 1)
    mapa(axs[2], mtz, "W1 da temperatura em z-score (escala do modelo)", 2)
    salvar(fig, "features_w1.png")

    fig, ax = plt.subplots(figsize=(6, 4.4))
    cols = [c for c in pres.columns if pres[c].sum() > 0]
    mapa_pres = pres[cols] * 100
    from matplotlib.colors import LinearSegmentedColormap
    ax.imshow(mapa_pres.values, cmap=LinearSegmentedColormap.from_list("seq", ["#f4f8fd"] + SEQ_AZUL),
              vmin=0, vmax=100, aspect="auto")
    for i in range(len(ordem)):
        for j in range(len(cols)):
            v = mapa_pres.values[i, j]
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=8, color="white" if v > 55 else TINTA)
    ax.set_xticks(range(len(cols)), cols); ax.set_yticks(range(len(ordem)), ordem)
    ax.grid(False); ax.tick_params(length=0, labelcolor=TINTA_2)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title("Edificações com cada medidor opcional no modelo")
    salvar(fig, "features_medidores.png")
    return desc, pres


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    aplicar_estilo()
    clientes = construir()
    q, resumo = quantidade(clientes)
    ordem = list(q.index)   # todos os gráficos na mesma ordem: do site com mais amostras ao com menos
    print(q.round(3).to_string(), "\n", resumo)
    print(rotulo(clientes, ordem).round(3).to_string())
    d, _ = features(clientes, ordem)
    print(d.round(3).to_string())


if __name__ == "__main__":
    main()
