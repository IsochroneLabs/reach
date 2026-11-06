// Attribution shown on the map and on the data page (arch. §10: always visible). On the map the
// basemap string already credits OpenStreetMap, which is also the source of our facilities and
// the routing network; the basemap's own TileJSON credit (OpenFreeMap) is added by MapLibre.
export const OSM_ATTRIBUTION =
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>'

export const DATA_ATTRIBUTION = [
  '<a href="https://www.zensus2022.de/" target="_blank" rel="noreferrer">Zensus 2022 © Destatis</a>',
  '<a href="https://www.nvbw.de/open-data" target="_blank" rel="noreferrer">GTFS © NVBW</a>',
]

export const BASEMAP_ATTRIBUTION: string = import.meta.env.VITE_BASEMAP_ATTRIBUTION
