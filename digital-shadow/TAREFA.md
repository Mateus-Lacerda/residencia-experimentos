# Tarefa: construir o Digital Shadow

Você está em `residencia-experimentos/digital-shadow/`, uma pasta nova. Construa aqui um protótipo
funcional da especificação em `ESPEC.md`, com os dados reais do BDG2 descritos abaixo. Trabalhe de
forma autônoma até ter algo rodando; não há ninguém para responder perguntas durante a execução.

## Regras obrigatórias

- **Nenhum emoji** em código de frontend (HTML, CSS, TS, TSX): nem em labels, botões, ícones,
  comentários, nada.
- **Não faça commits** nem mexa em git. Não adicione "Co-Authored-By" em lugar nenhum.
- **Não modifique nada fora de `digital-shadow/`.** Leia `../bdg2-fl/` à vontade, mas não altere
  arquivos lá. Há experimentos do usuário rodando na máquina: rode qualquer processo pesado com
  `nice -n 19` e um de cada vez.
- **Não invente dados.** Tudo o que for estimado ou sintético deve vir marcado com a proveniência
  (`observed` / `estimated` / `synthetic`) e aparecer assim na interface. Em particular, ainda **não
  existem previsões do modelo**: o campo "previsto" fica vazio e a interface mostra "sem previsão",
  nunca valores fictícios. Defina o formato em que as previsões serão importadas depois (ver abaixo).
- Interface em português do Brasil. Sem dependências carregadas de CDN em tempo de execução.

## Stack

Vite + React + TypeScript + Three.js (Three.js direto, organizado nos managers da especificação).
Gráficos do painel: SVG próprio ou uma biblioteca leve; escolha e justifique no README. Node 26 e
npm estão instalados.

## Dados

- Lista das 955 edificações do dataset: `../bdg2-fl/dataset/edificacoes.csv` (site, edificacao,
  uso_principal, area_m2, preenchimento e mediana de 2016 e 2017). Use só essas edificações.
- Metadados: `../bdg2-fl/data/raw/metadata.csv` (32 colunas; chave `building_id`).
- Consumo horário de eletricidade (kWh), 2016 e 2017: `../bdg2-fl/data/raw/electricity_cleaned.csv`
  (índice `timestamp`, uma coluna por edificação; há lacunas, que são ausência de leitura, não
  zero).
- Clima por site: `../bdg2-fl/data/raw/weather.csv` (opcional).

O ambiente Python do `bdg2-fl` tem pandas e numpy: escreva o script de exportação em
`digital-shadow/scripts/` e rode com `uv run --project ../bdg2-fl python scripts/<nome>.py`. Ele
gera JSON estático em `public/data/` (adicione `public/data/` a um `.gitignore` da pasta). Separe
geometria/metadados (um arquivo por site) de energia (por site, agregada, por exemplo diária; e
horária por edificação carregada sob demanda ao selecionar). Mantenha os arquivos com tamanho
razoável.

Cobertura dos metadados nas 955 edificações (%):

| coluna | cobertura | observação |
| :-- | --: | :-- |
| primaryspaceusage | 100 | 16 usos (Education 362, Office 193, Public services 124, Entertainment/public assembly 114, Lodging/residential 79, ...) |
| sub_primaryspaceusage | 100 | 82 usos detalhados |
| sqm | 100 | área construída |
| timezone | 100 | |
| lat, lng | 87 | coordenada do site, não do prédio (Eagle e Gator não têm) |
| yearbuilt | 36 | |
| industry, subindustry | 28 | |
| numberoffloors | 20 | 1 a 16, mediana 4 |
| energystarscore, eui, site_eui, source_eui | 14 | só Hog |
| heatingtype | 8 | |
| rating | 7 | |
| occupants | 6 | |
| chilledwater, steam, hotwater, gas, water | 36, 24, 13, 4, 2 | "Yes" = a edificação tem o medidor |

Por site (%): andares existem em Bear, Robin, Gator e Lamb (100) e Wolf (25); ano em Lamb (100),
Bear (99), Robin (83), Fox (71), Rat (47); setor em Fox, Robin, Wolf, Peacock, Lamb; aquecimento em
Robin e Lamb; ocupantes em Gator e Lamb; rating em Lamb e Robin. Bull e Eagle só têm o básico.

**Comece pelo site Lamb** (27 edificações, o de metadados mais completos) e generalize para os 11
sites com um seletor de site.

Regras para o que não existe na base:
- Altura: andares × pé-direito típico quando houver `numberoffloors`; senão, estimativa por uso e
  área (marcada `estimated`). Documente a regra no README.
- Footprint: derivado de área ÷ andares (reais ou estimados), com proporção por categoria.
- Posições, vias, árvores, estacionamentos e terreno: `synthetic`, layout determinístico (mesma
  entrada, mesma cena).
- EUI: consumo do período ÷ `sqm`, calculado a partir do consumo real.

## Previsões (para depois)

Defina e documente no README o formato de importação das previsões do modelo, por exemplo um CSV
`edificacao,timestamp,previsto_kwh` por site, e o script de exportação já deve aceitá-lo se existir
(e ignorar se não existir). A métrica "erro de previsão" fica desabilitada enquanto não houver
previsões.

## Entrega

1. `npm run build` sem erros e `npm run dev` funcionando.
2. README em português explicando: como gerar os dados, como rodar, a arquitetura, as regras de
   estimativa e os níveis de proveniência, o formato das previsões, e o que ficou de fora.
3. Verifique o que construiu: rode o build, confira que os JSON gerados batem com a contagem de
   edificações por site, e que nenhuma métrica trata lacuna como zero.
4. Ao terminar, escreva um resumo curto do que foi feito, o que foi verificado e o que falta.
