/** Junta os geradores: registros do site -> prédios posicionados, vias e vegetação. */

import type { Building, BuildingRecord } from "../domain/Building.ts";
import { generateBuilding } from "./BuildingGenerator.ts";
import { generateLayout, MARGEM_TERRENO, type SiteLayout } from "./CampusLayoutGenerator.ts";
import { generateRoads, type RoadNetwork } from "./RoadGenerator.ts";
import { generateVegetation, type Tree } from "./VegetationGenerator.ts";

export interface SiteModel {
  siteId: string;
  buildings: Building[];
  layout: SiteLayout;
  roads: RoadNetwork;
  trees: Tree[];
}

export function generateSite(siteId: string, records: BuildingRecord[]): SiteModel {
  const buildings = records.map((r) => generateBuilding(r, siteId));
  const layout = generateLayout(buildings);
  const roads = generateRoads(layout);
  const trees = generateVegetation(siteId, [...layout.green, ...roads.greenFill], layout.terrain, MARGEM_TERRENO);
  return { siteId, buildings, layout, roads, trees };
}
