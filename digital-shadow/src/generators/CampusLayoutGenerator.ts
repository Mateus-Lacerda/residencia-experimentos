/**
 * CampusLayoutGenerator: posiciona os prédios num campus sintético.
 *
 * O BDG2 não tem coordenadas por prédio (lat/lng é do site), então todo o layout é
 * "synthetic" e determinístico: mesma lista de prédios, mesma cena.
 *
 * Algoritmo (rectangle packing com zoneamento funcional):
 * 1. Cada prédio vira um lote: footprint (rotacionado 0 ou 90 graus por hash do id) + recuo
 *    proporcional ao tamanho + estacionamento para usos que costumam ter um.
 * 2. Os prédios são agrupados por zona funcional (acadêmica, administrativa, ...). Zonas
 *    grandes viram várias quadras de até QUADRA_MAX lotes.
 * 3. Dentro de cada quadra, os lotes são empacotados em prateleiras (shelf packing), maiores
 *    primeiro, com caminhos de pedestres entre as prateleiras e sobra como área verde.
 * 4. As quadras são empacotadas em fileiras, na ordem das zonas, separadas por vias.
 * Não há sobreposição por construção: cada lote ocupa uma célula exclusiva.
 */

import type { Building } from "../domain/Building.ts";
import type { Rect } from "../utils/geometry.ts";
import { clamp, hashString, seededRandom } from "../utils/geometry.ts";

export interface Zone {
  id: string;
  label: string;
  usos: string[];
}

export const ZONAS: Zone[] = [
  { id: "academica", label: "Zona acadêmica", usos: ["Education", "Technology/science"] },
  { id: "administrativa", label: "Zona administrativa", usos: ["Office", "Public services", "Services"] },
  {
    id: "convivencia",
    label: "Zona de convivência",
    usos: ["Entertainment/public assembly", "Religious worship", "Retail", "Food sales and service"],
  },
  { id: "saude", label: "Zona de saúde", usos: ["Healthcare"] },
  { id: "residencial", label: "Zona residencial", usos: ["Lodging/residential"] },
  { id: "apoio", label: "Zona de apoio", usos: ["Parking", "Warehouse/storage", "Manufacturing/industrial", "Utility", "Other"] },
];

const USOS_COM_ESTACIONAMENTO = new Set([
  "Office", "Healthcare", "Entertainment/public assembly", "Public services", "Retail", "Food sales and service",
]);

export const QUADRA_MAX = 10;
/** largura do vão entre quadras: calçada + via + calçada (m) */
export const VAO_QUADRAS = 20;
export const CALCADA = 3;
const CAMINHO = 5;
export const MARGEM_TERRENO = 45;

export interface ParkingLot {
  rect: Rect;
  /** fileiras de vagas correm ao longo de x */
  rows: number;
}

export interface Block {
  rect: Rect;
  zone: Zone;
}

export interface SiteLayout {
  terrain: Rect;
  /** extensão ocupada pelas quadras (sem margem) */
  extent: Rect;
  blocks: Block[];
  /** fileiras globais de quadras, usadas pelo RoadGenerator */
  rows: { z: number; d: number; blocks: Rect[] }[];
  lots: Rect[];
  paths: Rect[];
  green: Rect[];
  parking: ParkingLot[];
}

interface Lot {
  b: Building;
  w: number;
  d: number;
  /** recuo */
  s: number;
  bw: number;
  bd: number;
  parkingDepth: number;
}

function makeLot(b: Building): Lot {
  const rnd = seededRandom(hashString(`${b.id}:lote`));
  const rot = rnd() < 0.5 ? 0 : Math.PI / 2;
  b.position.rotation = rot;
  const bw = rot === 0 ? b.geometry.width : b.geometry.depth;
  const bd = rot === 0 ? b.geometry.depth : b.geometry.width;
  const s = clamp(0.12 * Math.sqrt(b.geometry.footprint), 5, 15);
  let parkingDepth = 0;
  if (USOS_COM_ESTACIONAMENTO.has(b.usage) && b.attributes.area > 2500) {
    // módulo de 16 m = duas fileiras de vagas de 5 m + corredor de 6 m
    parkingDepth = b.attributes.area > 15000 ? 32 : 16;
  }
  const d = s + bd + (parkingDepth ? s * 0.6 + parkingDepth : 0) + s;
  return { b, w: bw + 2 * s, d, s, bw, bd, parkingDepth };
}

interface PackedBlock {
  w: number;
  d: number;
  zone: Zone;
  /** posições relativas ao canto da quadra */
  cells: { lot: Lot; x: number; z: number }[];
  paths: Rect[];
  green: Rect[];
}

function packBlock(lots: Lot[], zone: Zone): PackedBlock {
  const soma = lots.reduce((a, l) => a + l.w * l.d, 0);
  const alvo = Math.max(Math.max(...lots.map((l) => l.w)), Math.sqrt(soma) * 1.25);
  const linhas: { lots: Lot[]; w: number; d: number }[] = [];
  let atual: { lots: Lot[]; w: number; d: number } | null = null;
  for (const l of lots) {
    if (!atual || (atual.w + l.w > alvo && atual.lots.length > 0)) {
      atual = { lots: [], w: 0, d: 0 };
      linhas.push(atual);
    }
    atual.lots.push(l);
    atual.w += l.w;
    atual.d = Math.max(atual.d, l.d);
  }
  const W = Math.max(...linhas.map((r) => r.w));
  const cells: PackedBlock["cells"] = [];
  const paths: Rect[] = [];
  const green: Rect[] = [];
  let z = 0;
  linhas.forEach((r, i) => {
    // distribui a sobra da linha entre os lotes, para a quadra fechar retangular
    const extra = (W - r.w) / r.lots.length;
    let x = 0;
    for (const l of r.lots) {
      const cw = l.w + extra;
      cells.push({ lot: l, x: x + extra / 2, z });
      if (extra > 4) {
        green.push({ x, z, w: extra / 2, d: r.d }, { x: x + extra / 2 + l.w, z, w: extra / 2, d: r.d });
      }
      if (r.d - l.d > 4) green.push({ x: x + extra / 2, z: z + l.d, w: l.w, d: r.d - l.d });
      x += cw;
    }
    z += r.d;
    if (i < linhas.length - 1) {
      paths.push({ x: 0, z, w: W, d: CAMINHO });
      z += CAMINHO;
    }
  });
  return { w: W, d: z, zone, cells, paths, green };
}

export function generateLayout(buildings: Building[]): SiteLayout {
  const lots = buildings.map(makeLot);
  const porZona = new Map<string, Lot[]>();
  for (const l of lots) {
    const z = ZONAS.find((zz) => zz.usos.includes(l.b.usage)) ?? ZONAS[ZONAS.length - 1];
    if (!porZona.has(z.id)) porZona.set(z.id, []);
    porZona.get(z.id)!.push(l);
  }

  const quadras: PackedBlock[] = [];
  for (const zona of ZONAS) {
    const ls = porZona.get(zona.id);
    if (!ls) continue;
    // maiores primeiro; desempate pelo id para determinismo
    ls.sort((a, b) => b.w * b.d - a.w * a.d || (a.b.id < b.b.id ? -1 : 1));
    const nQuadras = Math.ceil(ls.length / QUADRA_MAX);
    const grupos: Lot[][] = Array.from({ length: nQuadras }, () => []);
    // distribuição em serpentina para equilibrar o tamanho das quadras
    ls.forEach((l, i) => {
      const r = Math.floor(i / nQuadras);
      const k = r % 2 === 0 ? i % nQuadras : nQuadras - 1 - (i % nQuadras);
      grupos[k].push(l);
    });
    for (const g of grupos) quadras.push(packBlock(g, zona));
  }

  // fileiras de quadras (na ordem das zonas, preservando o agrupamento funcional)
  const somaQ = quadras.reduce((a, q) => a + (q.w + VAO_QUADRAS) * (q.d + VAO_QUADRAS), 0);
  const alvo = Math.max(Math.max(...quadras.map((q) => q.w)), Math.sqrt(somaQ) * 1.15);
  const fileiras: { qs: PackedBlock[]; w: number; d: number }[] = [];
  let f: { qs: PackedBlock[]; w: number; d: number } | null = null;
  for (const q of quadras) {
    const add = (f && f.qs.length ? VAO_QUADRAS : 0) + q.w;
    if (!f || (f.w + add > alvo && f.qs.length > 0)) {
      f = { qs: [], w: 0, d: 0 };
      fileiras.push(f);
    }
    f.w += (f.qs.length ? VAO_QUADRAS : 0) + q.w;
    f.qs.push(q);
    f.d = Math.max(f.d, q.d);
  }

  const blocks: Block[] = [];
  const rows: SiteLayout["rows"] = [];
  const outLots: Rect[] = [];
  const paths: Rect[] = [];
  const green: Rect[] = [];
  const parking: ParkingLot[] = [];
  const larguraTotal = Math.max(...fileiras.map((r) => r.w));
  let z = 0;
  for (const r of fileiras) {
    // centraliza a fileira na largura total
    let x = (larguraTotal - r.w) / 2;
    const row = { z, d: r.d, blocks: [] as Rect[] };
    for (const q of r.qs) {
      const oz = z + (r.d - q.d) / 2;
      const rect = { x, z: oz, w: q.w, d: q.d };
      blocks.push({ rect, zone: q.zone });
      row.blocks.push(rect);
      if (r.d - q.d > 4) {
        green.push({ x, z, w: q.w, d: (r.d - q.d) / 2 }, { x, z: oz + q.d, w: q.w, d: (r.d - q.d) / 2 });
      }
      for (const p of q.paths) paths.push({ ...p, x: p.x + x, z: p.z + oz });
      for (const g of q.green) green.push({ ...g, x: g.x + x, z: g.z + oz });
      for (const c of q.cells) {
        const l = c.lot;
        const lx = x + c.x;
        const lz = oz + c.z;
        outLots.push({ x: lx, z: lz, w: l.w, d: l.d });
        l.b.position.x = lx + l.s + l.bw / 2;
        l.b.position.z = lz + l.s + l.bd / 2;
        if (l.parkingDepth) {
          parking.push({
            rect: { x: lx + l.s, z: lz + l.s + l.bd + l.s * 0.6, w: l.bw, d: l.parkingDepth },
            rows: l.parkingDepth / 8,
          });
        }
      }
      x += q.w + VAO_QUADRAS;
    }
    rows.push(row);
    z += r.d + VAO_QUADRAS;
  }
  const alturaTotal = z - VAO_QUADRAS;

  // centraliza tudo na origem
  const cx = larguraTotal / 2;
  const cz = alturaTotal / 2;
  const mv = (rc: Rect) => {
    rc.x -= cx;
    rc.z -= cz;
  };
  blocks.forEach((b) => mv(b.rect));
  outLots.forEach(mv);
  paths.forEach(mv);
  green.forEach(mv);
  parking.forEach((p) => mv(p.rect));
  rows.forEach((r) => {
    r.z -= cz;
  });
  for (const b of buildings) {
    b.position.x -= cx;
    b.position.z -= cz;
  }

  const extent = { x: -cx, z: -cz, w: larguraTotal, d: alturaTotal };
  const terrain = {
    x: extent.x - MARGEM_TERRENO,
    z: extent.z - MARGEM_TERRENO,
    w: extent.w + 2 * MARGEM_TERRENO,
    d: extent.d + 2 * MARGEM_TERRENO,
  };
  return { terrain, extent, blocks, rows, lots: outLots, paths, green, parking };
}
