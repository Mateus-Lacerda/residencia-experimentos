# Digital Shadow (BDG2)

Protótipo de visualização 3D por site das 955 edificações do dataset do `bdg2-fl`, com consumo
horário real de eletricidade de 2016 e 2017. A especificação está em `ESPEC.md` e as instruções de
execução em `TAREFA.md`.

É um Digital Shadow: a cena acompanha os dados medidos e não simula o funcionamento dos prédios. O
BDG2 não tem planta nem coordenadas por prédio, então terreno, posições e vias são gerados por
procedimento e aparecem marcados como sintéticos.

## Como gerar os dados

Requer o ambiente Python do `../bdg2-fl` (pandas e numpy) e os arquivos em `../bdg2-fl/data/raw/`.

```sh
npm run dados      # = nice -n 19 uv run --project ../bdg2-fl python scripts/exportar_dados.py
```

O script lê `../bdg2-fl/dataset/edificacoes.csv` (só essas 955 edificações), `metadata.csv`,
`electricity_cleaned.csv` e `weather.csv`, e grava JSON estático em `public/data/` (fora do git,
ver `.gitignore`). Leva cerca de 1 a 2 minutos e ocupa 102 MB:

| arquivo | conteúdo | tamanho |
| :-- | :-- | --: |
| `sites.json` | índice dos 11 sites (contagem, categoria, área, fuso, coordenada do site) | 4 KB |
| `sites/<Site>/edificacoes.json` | metadados das edificações; a geometria é gerada no navegador | 16 a 124 KB |
| `sites/<Site>/energia_diaria.json` | por edificação e dia: soma das horas lidas e número de horas lidas; temperatura média diária do site | 180 KB a 1,9 MB |
| `sites/<Site>/horario/<edificacao>.json` | 17.544 valores horários, carregado só ao selecionar o prédio | 80 a 140 KB |

Lacuna é ausência de leitura, nunca zero: horas sem leitura viram `null`, dias sem nenhuma hora lida
viram `null`, e cada soma diária vem com o número de horas que a compõem. Leituras muito pequenas
(Lamb tem valores de 0,0025 kWh) mantêm 3 algarismos significativos em vez de arredondar para 0.

## Como rodar

```sh
npm install
npm run dados       # uma vez, ou quando houver previsões novas
npm run dev         # http://localhost:5173
npm run build       # tsc + vite build em dist/ (copia public/data junto)
npm run verificar   # verificações descritas abaixo
```

O site inicial é Lamb (27 edificações, o de metadados mais completos); o seletor no cabeçalho troca
entre os 11 sites.

## Interface

- Cabeçalho: seletor de site, categoria da instalação (inferida do uso dominante, marcada
  "estimado"), indicadores do período (edificações, consumo, EUI do site, área), período, métrica,
  escala e legenda.
- Período: 2016 a 2017, ano, mês, semana ou dia, com controle deslizante, anterior/próximo e
  "Reproduzir", que avança o período a cada 0,9 s e recolore a cena.
- Cena: câmera ortográfica isométrica. Arrastar gira, scroll aproxima, botão direito desloca,
  "Resetar visão" volta ao enquadramento inicial. Hover destaca o contorno e mostra uma dica; clique
  seleciona; clique no terreno ou Esc remove a seleção.
- Estado A (sem seleção): todos os prédios na cor da métrica; o painel lista o ranking, a
  composição de usos e o resumo de proveniência.
- Estado B (prédio selecionado): o prédio mantém a cor e ganha contorno, os demais são dessaturados.
  Abas: visão geral, histórico energético (barras mensais clicáveis, série diária de dois anos),
  previsão, características construtivas, sistemas e medidores. O gráfico real x previsto usa a
  série horária para períodos de até 31 dias e a diária acima disso.

### Métricas

A métrica padrão é EUI, porque consumo absoluto compara tamanho e não eficiência.

| métrica | definição | escala |
| :-- | :-- | :-- |
| EUI | consumo do período / `sqm` (kWh/m²) | sequencial |
| Consumo absoluto | kWh no período | sequencial |
| Erro de previsão | (previsto - real) / real, só nas horas que têm leitura e previsão | divergente, centrada em 0 |
| Desvio da referência | média horária no período vs. média horária do próprio prédio em 2016 e 2017 | divergente |
| Variação temporal | média horária no período vs. período anterior de mesma duração | divergente |

Regra de cobertura (`src/domain/EnergyMetrics.ts`), com cobertura = horas lidas / horas do período:

- 100%: valor observado (soma das leituras).
- de 50% a 100%: total estimado como média horária lida x horas do período, marcado "estimado".
- abaixo de 50%: sem dado, cinza na cena e "sem dado" no painel.

Desvio e variação são razões entre médias de horas lidas, sem extrapolação, e ficam "real" quando
as duas janelas têm pelo menos 50% de cobertura. Variação fica indisponível quando não existe
período anterior dentro de 2016 e 2017.

A escala da cor é calculada a cada período sobre os valores do site, sem limites fixos: percentis 5
a 95 (padrão; valores fora saturam), mínimo a máximo, ou logarítmica (só nas sequenciais). As
divergentes são simétricas em torno de zero. "Sem dado" usa um cinza que não pertence a nenhuma das
paletas.

## Arquitetura

```
src/
  components/   DigitalShadow, SiteHeader, SceneCanvas, SceneControls, BuildingPanel, SitePanel,
                EnergyLegend, ProvenanceBadge, charts/ (LineChart, BarChart em SVG)
  controller/   DigitalShadowController: estado (site, período, métrica, seleção), eventos
  engine/       SceneManager, CameraManager, TerrainRenderer, BuildingRenderer, EnergyManager,
                EnergyRenderer, InteractionManager
  generators/   BuildingGenerator, CampusLayoutGenerator, RoadGenerator, VegetationGenerator, SiteGenerator
  domain/       Building, Site (tipos e carga dos JSON), Period, EnergyMetrics
  utils/        geometry, colorScale, normalization, format
```

O React só lê um snapshot do controller (`useSyncExternalStore`) e chama ações. O controller gera a
cena uma vez por site (`generateSite`) e a entrega ao `SceneManager`. Mudanças de período, métrica,
escala ou seleção passam pelo `EnergyManager` (somas prefixadas por prédio, consulta de período em
O(1), domínio da escala) e chegam ao `EnergyRenderer`, que só reescreve as cores das instâncias. A
geometria não é reconstruída, e uma previsão nova muda só os dados de energia.

Renderização: um `InstancedMesh` por uso para os prédios e um por camada do terreno (vias,
calçadas, lotes, estacionamentos, faixas de vagas, árvores), com `MeshLambertMaterial`, sem
sombras, sem texturas e sem pós-processamento. Pixel ratio limitado a 1,5. O quadro só é desenhado
quando algo muda (câmera, cor, contorno, tamanho). O raycast usa `instanceId` para achar o prédio.

Medido com `scripts/capturar.mjs` no Chrome (janela 1600 x 950): Lamb com 19 draw calls e 42 peças
de prédio, Rat (247 prédios) com 23 draw calls e 370 peças; geração da cena em 2 a 5 ms, carga do
site abaixo de 150 ms no servidor local, cerca de 60 fps girando a câmera (limitado pelo vsync).

Gráficos: SVG próprio (`components/charts/`). São só duas formas (linha com lacunas e barras com
hachura para "sem dado"), e uma biblioteca acrescentaria peso sem resolver a regra de lacuna, que
precisa ser explícita de qualquer forma.

## Regras de estimativa

Definidas em `src/generators/BuildingGenerator.ts` (tabela `PERFIS`):

| uso | pé-direito (m) | footprint de referência (m²) | máx. andares | proporção L:P | template |
| :-- | --: | --: | --: | --: | :-- |
| Education | 3,8 | 1.500 | 6 | 1,6 | acadêmico (bloco + ala em L) |
| Office | 3,6 | 900 | 12 | 1,2 | torre (embasamento + torre recuada a partir de 4 andares) |
| Public services | 3,6 | 1.100 | 6 | 1,4 | bloco |
| Entertainment/public assembly | 6,0 | 3.000 | 3 | 1,3 | auditório (salão + caixa cênica) |
| Lodging/residential | 3,0 | 700 | 10 | 2,6 | lâminas paralelas |
| Healthcare | 4,2 | 1.400 | 10 | 1,4 | hospital (embasamento + bloco alto) |
| Parking | 3,0 | 2.500 | 6 | 1,8 | garagem (lajes) |
| Warehouse/storage | 7,0 | 6.000 | 1 | 1,8 | galpão |
| Manufacturing/industrial | 6,5 | 5.000 | 2 | 1,7 | galpão |
| demais usos | 3,5 a 6,0 | 1.000 a 3.000 | 2 a 6 | 1,4 a 1,8 | bloco, acadêmico ou galpão |

- Andares: `numberoffloors` quando existe ("real"); senão `round(sqrt(área / footprint de
  referência))`, limitado a [1, máx. andares] ("estimado").
- Altura: andares x pé-direito típico do uso. É sempre "estimado", porque o pé-direito não está na
  base; o painel diz se os andares eram reais ou estimados.
- Footprint: área / andares, com a proporção da categoria variando ±15% por hash do id ("estimado").
- Posição, rotação (0 ou 90 graus por hash do id), terreno, vias, calçadas, áreas verdes, árvores e
  estacionamentos: "sintético".
- Layout (`CampusLayoutGenerator`): cada prédio vira um lote (footprint + recuo de 5 a 15 m +
  estacionamento de 16 ou 32 m para escritório, saúde, reunião pública, serviços públicos e
  comércio acima de 2.500 m²). Os lotes são agrupados por zona funcional (acadêmica, administrativa,
  convivência, saúde, residencial, apoio), divididos em quadras de até 10 lotes e empacotados em
  prateleiras, maiores primeiro. As quadras são empacotadas em fileiras separadas por vias de 14 m
  com calçadas de 3 m, dentro de um anel viário e de um terreno com margem de 45 m. Não há
  sobreposição por construção, e a mesma lista de prédios gera sempre a mesma cena.
- EUI: consumo real do período / `sqm`. O EUI cadastrado do BDG2 (só Hog) aparece à parte, como dado
  da base.

## Níveis de proveniência

Todo valor no painel tem uma etiqueta:

- **real** (`observed`): presente na base. Área, uso, uso detalhado, andares cadastrados, ano,
  ocupantes, setor, rating, medidores, consumo com cobertura completa.
- **estimado** (`estimated`): inferido. Altura, footprint, dimensões, andares ausentes, totais de
  períodos com cobertura parcial, categoria do site.
- **sintético** (`synthetic`): criado para completar a cena. Posições, terreno, vias, árvores,
  estacionamentos.
- **sem dado**: não existe na base, ou a cobertura de leituras no período é menor que 50%.

## Formato das previsões

Ainda não há previsões do modelo. O campo "previsto" fica vazio, a interface mostra "sem previsão" e
a métrica de erro fica desabilitada.

Para importar, crie `previsoes/<Site>.csv` (um arquivo por site, ex.: `previsoes/Lamb.csv`):

```csv
edificacao,timestamp,previsto_kwh
Lamb_assembly_Katelyn,2017-01-01 00:00:00,18.42
Lamb_assembly_Katelyn,2017-01-01 01:00:00,17.90
```

- `edificacao`: id do BDG2, igual à coluna de `electricity_cleaned.csv`.
- `timestamp`: hora local do site, no formato do BDG2 (`AAAA-MM-DD HH:MM:SS`), início da hora,
  entre 2016-01-01 00:00 e 2017-12-31 23:00.
- `previsto_kwh`: consumo previsto da hora, em kWh.

Depois rode `npm run dados`. O exportador descarta linhas com data ou valor inválido, edificações
de outro site e duplicatas (fica a última), e avisa no terminal. Arquivo ausente é ignorado. Para
cada prédio, `energia_diaria.json` passa a ter a soma prevista diária e as somas pareadas (previsto
e real só nas horas que têm os dois), que alimentam o erro; os arquivos horários ganham a série
`previsto`. O teste `scripts/testar_previsoes.py` exercita esse caminho com um CSV temporário e
não grava nada em `public/data`.

## Verificação

`npm run verificar` roda três scripts:

- `scripts/verificar_dados.py`: contagem e ids por site batem com `edificacoes.csv` (955 no total);
  a ordem dos ids é a mesma nos arquivos de metadados e de energia; cada série horária tem as
  mesmas lacunas, os mesmos zeros e os mesmos valores do CSV; cada dia `null` corresponde a 0 horas
  lidas e cada soma diária bate com as horas lidas.
- `scripts/verificar_cena.ts`: roda o mesmo TypeScript do navegador. Confere o número de prédios
  gerados por site, ausência de sobreposição entre prédios, peças dos templates dentro do
  footprint, determinismo (duas gerações iguais) e casos de lacuna: prédio sem leitura dá `null` e
  não 0, cobertura de 40% dá sem dado, 50% dá estimado, erro sem previsões fica indisponível e erro
  com previsões dá +10% num caso montado. Nos dados reais, nenhum prédio sem horas lidas ou com
  cobertura abaixo de 50% recebe valor.
- `scripts/testar_previsoes.py`: importação do formato de previsões.

`scripts/capturar.mjs` abre a aplicação no Chrome instalado (playwright-core), tira capturas de
tela, mede FPS e lista erros de console:
`node scripts/capturar.mjs http://localhost:5173/ Rat capturas mes 6 desvio`.

## O que ficou de fora

- Outros medidores (água gelada, vapor, água quente, gás): o painel mostra só se o medidor existe;
  as séries não são carregadas.
- Clima: a temperatura média diária é exportada em `energia_diaria.json`, mas a interface ainda
  não a mostra.
- Rótulos de zona na cena, filtros por uso e busca por prédio.
- Fuso: datas tratadas como hora local do site, como no BDG2, sem conversão.
- O bundle JS tem 844 KB (228 KB gzip), quase todo Three.js; não foi dividido.
- `npm run build` copia os 102 MB de `public/data` para `dist/`. Para publicar, os dados horários
  deveriam ir para um armazenamento separado ou ser compactados.
- As metas de desempenho foram medidas numa só máquina (Mac com Chrome), não em hardware modesto.
