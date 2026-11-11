# bdg2-fl

Aprendizado federado (FedAvg) sobre o Building Data Genome Project 2 (BDG2). Cada site do BDG2 é um
cliente, e a tarefa é prever o consumo de eletricidade da próxima hora de cada edificação. O treino
usa 2016 e a validação usa 2017.

## Como rodar

```
uv sync
uv run python -m bdg2_fl.download   # baixa os CSVs do BDG2 para data/raw/ (~360 MB, só na primeira vez)
```

Depois abra os notebooks com o kernel do ambiente do projeto:

- `eda.ipynb`: modalidades por site, seleção dos clientes, um problema de qualidade nos dados e as
  diferenças entre os clientes (escala, perfil horário, resposta à temperatura).
- `treinamento.ipynb`: FedAvg, comparação com treino centralizado, só local e random walk (prever
  que a próxima hora repete a atual), teste de não-IID entre sites e conclusão. Roda em ~1 min e meio num notebook comum, em CPU.

## Estrutura

```
src/bdg2_fl/config.py      parâmetros do experimento
src/bdg2_fl/download.py    download dos CSVs (o repositório do BDG2 usa Git LFS)
src/bdg2_fl/dados.py       seleção de sites e edificações, features, normalização, split
src/bdg2_fl/modelo.py      MLP e laço de treino
src/bdg2_fl/fedavg.py      FedAvg escrito à mão, com log por rodada
src/bdg2_fl/baselines.py   treino centralizado e só local
src/bdg2_fl/metricas.py    RMSE e CV(RMSE)
src/bdg2_fl/graficos.py    estilo e cores dos gráficos
```

## Resultado (validação 2017, CV(RMSE) %)

| Site  | FedAvg | Centralizado | Só local | Random walk |
|-------|-------:|-------------:|---------:|------------:|
| Rat   | 16,4   | 21,2         | **12,2** | 16,8        |
| Hog   | 15,7   | 16,6         | **15,5** | 16,6        |
| Fox   | 7,2    | 7,0          | **6,8**  | 8,8         |
| Bull  | 17,7   | 16,8         | **16,6** | 18,5        |
| Eagle | 7,4    | 7,3          | **7,3**  | 8,7         |
| Bear  | 9,1    | 8,5          | **8,2**  | 13,8        |
| Total | 13,3   | 15,7         | **11,2** | 14,4        |

O FedAvg ganha do random walk em todos os sites, mas por menos de 1 ponto em Rat, Hog e Bull. O
treino só local ganha em todos os sites. Os clientes são não-IID: o modelo local de um site, aplicado
em outro, erra de 1,10 a 2,52 vezes mais que o modelo local daquele site. A conclusão do notebook de
treinamento discute por que isso acontece e quais métodos de FL personalizado testar a seguir.
