# Especificação: Digital Shadow 3D de instalações consumidoras de energia

Texto da especificação fornecida pelo usuário (sem os links de imagens de referência). As
instruções de execução, com os dados reais disponíveis, estão em `TAREFA.md`.

## 1. Conceito do produto

O sistema terá uma visualização independente para cada `site`. Um site representa uma instalação
física ou complexo de edificações, como uma universidade, hospital, escola ou conjunto corporativo.

A representação terá três características fundamentais:

1. **Identidade espacial:** o usuário reconhece o local como um complexo de edifícios, e não como
   uma coleção de gráficos.
2. **Identidade energética:** cada edifício apresenta visualmente seu comportamento energético.
3. **Identidade temporal:** a cena responde ao período selecionado, permitindo observar como o
   consumo muda ao longo do tempo.

É um Digital Shadow, não um Digital Twin: a representação acompanha o estado dos dados reais, mas
não simula fisicamente o funcionamento dos edifícios.

## 2. Interface

Três regiões: cabeçalho contextual, cena 3D e painel de informações.

### 2.1. Cabeçalho contextual

Nome do site, categoria da instalação, quantidade de edifícios, período selecionado, métrica de
visualização e legenda de cores. Indicadores resumidos (consumo no período, EUI, nº de edifícios).

### 2.2. Cena 3D: visão geral

Terreno com dimensões proporcionais ao complexo, edificações individuais, vias internas e
calçadas, áreas verdes, estacionamentos quando aplicável, elementos complementares simplificados.
Os prédios são selecionáveis individualmente.

| Interação         | Comportamento           |
| ----------------- | ----------------------- |
| Clique no prédio  | Seleciona a edificação  |
| Hover             | Destaca o contorno      |
| Arrastar          | Rotaciona a câmera      |
| Scroll            | Zoom                    |
| Botão de reset    | Retorna à visão inicial |
| Clique no terreno | Remove seleção          |

Câmera ortográfica, perspectiva isométrica.

### 2.3. Visualização híbrida de energia

**Estado A, nenhum edifício selecionado:** todos os edifícios têm a cor da métrica energética
escolhida. Escala configurável e baseada na métrica, sem limites fixos universais.

**Estado B, edifício selecionado:** o edifício recebe destaque e os demais ficam dessaturados. Um
painel lateral mostra: nome, uso e uso detalhado, consumo atual, consumo previsto, área, andares e
um gráfico de consumo real × previsto. Abas: visão geral, histórico energético, previsão,
características construtivas, sistemas e medidores.

Não mostrar consumo absoluto como se fosse eficiência: para comparar edifícios de tamanhos
diferentes, oferecer EUI (consumo por área).

## 3. Arquitetura de renderização

Sem motor gráfico complexo, sem backend de renderização, sem Blender, sem servidor de geometria. A
geometria é gerada uma vez, no carregamento do site, e reutilizada.

Camadas: Dashboard React (cabeçalho, filtros, painel, gráficos) → Digital Shadow Controller
(seleção, estado temporal, métricas, eventos) → Scene Manager (terreno e edifícios) e Energy
Manager (heatmap e estados) → Three.js Renderer (WebGL, instancing, raycasting, câmera).

| Componente   | Tecnologia                        |
| ------------ | --------------------------------- |
| Interface    | React                             |
| Renderização | Three.js                          |
| Linguagem    | TypeScript                        |
| Geometria    | Procedural em TypeScript          |
| Dados        | JSON estático                     |

Estrutura sugerida:

```
src/
├── components/   DigitalShadow.tsx, SceneCanvas.tsx, BuildingPanel.tsx, EnergyLegend.tsx, SceneControls.tsx
├── engine/       SceneManager.ts, CameraManager.ts, BuildingRenderer.ts, TerrainRenderer.ts,
│                 InteractionManager.ts, EnergyRenderer.ts
├── generators/   BuildingGenerator.ts, CampusLayoutGenerator.ts, RoadGenerator.ts, VegetationGenerator.ts
├── domain/       Building.ts, Site.ts, EnergyMetrics.ts
└── utils/        geometry.ts, colorScale.ts, normalization.ts
```

A separação mais importante é entre `BuildingGenerator` (constrói o prédio) e `EnergyRenderer`
(muda a aparência conforme os dados). Uma nova previsão não reconstrói a geometria.

## 4. Geração procedural

Gerador orientado a categorias de uso, não um gerador de cidade genérico. Templates por categoria
(ex.: Education: blocos acadêmicos e áreas abertas; Healthcare: blocos hospitalares; Office:
torres e estacionamentos; Warehouse: galpões e pátios), compostos por primitivas reutilizáveis.

Modelo intermediário, independente do dataset:

```ts
interface Building {
  id: string; siteId: string; usage: string; subUsage?: string;
  geometry: { width: number; depth: number; height: number; floors?: number; estimatedFloors: boolean };
  position: { x: number; z: number; rotation: number };
  attributes: { area: number; yearBuilt?: number; occupants?: number };
  systems: { chilledWater: boolean; steam: boolean; hotWater: boolean; gas: boolean; water: boolean };
  energy: { actual?: number; predicted?: number; eui?: number; rating?: string };
}
type DataOrigin = "observed" | "estimated" | "synthetic";
```

Proveniência por atributo: uma altura estimada não aparece como dado cadastral.

Layout: sem coordenadas individuais, então layout procedural (rectangle packing com zoneamento
funcional): área total estimada, distribuição respeitando dimensões, agrupamento por função,
espaço de circulação, áreas verdes, sem sobreposição. O terreno e as posições são sintéticos e
devem ser apresentados assim.

## 5. Performance

InstancedMesh por lote (categoria/material), BufferGeometry, MeshLambertMaterial,
OrthographicCamera, Raycaster com instanceId, frustum culling. Sem sombras dinâmicas por edifício,
sem pós-processamento, sem texturas de alta resolução, sem GLB de terceiros, sem milhares de labels
DOM, resolução limitada em telas de alta densidade, renderização suspensa quando a cena está
parada. Metas a validar: cena em até ~2 s, ~60 FPS em desktop, interação sem reconstrução.

## 6. Dados energéticos

Geometria carregada uma vez por site; dados energéticos por período, separados. Fluxo: seleção de
período → dados reais e previstos → Energy Manager normaliza → EnergyRenderer atualiza as cores das
instâncias, sem reconstruir a geometria.

Métricas selecionáveis: consumo absoluto, EUI, erro de previsão (escala divergente centrada em
zero), desvio de referência, variação temporal. Métrica padrão para comparar edifícios: EUI.
Valores ausentes como categoria visual própria (cinza ou hachurado), nunca como zero.

## 7. Roadmap

1. Engine 3D básica (cena, câmera ortográfica, terreno, prédios retangulares, seleção por clique).
2. Gerador procedural (registros → edifícios, alturas estimadas, dimensões, layout, templates).
3. Camada energética (heatmap, consumo real, previsões, métricas, painel).
4. Otimização (instancing, menos draw calls, carregamento, FPS e memória).
5. Integração (seleção de sites, filtros temporais, gráficos, responsividade).

## 9. Níveis de confiabilidade

- **Real:** presente na base (ex.: área construída).
- **Estimado:** inferido (ex.: altura sem número de andares).
- **Sintético:** criado para completar o cenário (árvores, vias, estacionamentos, posições).

Começar por um site, o de mais informação construtiva, validar o gerador e depois generalizar.
