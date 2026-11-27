# Basemap (D5, notes N18)

`tuebingen.geojson` is a simplified extract of public OpenStreetMap data: roads, water, green
spaces and rail around Tübingen, in EPSG:4326. `style.json` is the hand-written monochrome
MapLibre style that draws it. Both are served from **our own origin** with the static build; the
app never contacts a tile host, font CDN or other third party (A6).

- Source: `data/raw/<run_id>/osm/tuebingen-regbez-latest.osm.pbf` (27 Nov 2026 for the current
  file), © OpenStreetMap contributors, ODbL.
- Size: 4.5 MB, 21,017 features, z 11–17. The file is simplified, not a full map: buildings,
  footpaths and labels are left out for now.
- Production target remains the vector-tile build of N18 (unpacked `z/x/y.pbf`, self-hosted
  glyphs). This GeoJSON is the demo implementation until that build exists.

## Regenerate

```sh
# 1. Clip the region extract to the routing area and keep the map layers
osmium extract -b 8.90,48.41,9.19,48.63 -o /tmp/basemap/tuebingen.osm.pbf \
  -O data/raw/<run_id>/osm/tuebingen-regbez-latest.osm.pbf
osmium tags-filter /tmp/basemap/tuebingen.osm.pbf -o /tmp/basemap/base.osm.pbf -O \
  w/highway w/railway w/waterway w/water w/natural=water w/natural=wood \
  w/landuse=forest w/landuse=meadow w/landuse=grass w/landuse=reservoir \
  w/landuse=cemetery w/landuse=vineyard w/landuse=orchard \
  w/leisure=park w/leisure=garden w/leisure=playground
osmium export /tmp/basemap/base.osm.pbf -f geojsonseq \
  -o /tmp/basemap/base.geojsonseq --geometry-types=polygon,linestring -a type,id

# 2. Simplify and write the feature collection
uv run --package reach-pipeline python web/scripts/make-basemap.py \
  --input /tmp/basemap/base.geojsonseq --output web/public/basemap/tuebingen.geojson
```

`style.json` only reads the two properties `kind` (`road`, `path` is not emitted, `rail`,
`water`, `waterway`, `forest`, `green`) and `class` (`major`, `minor` for roads).

## University buildings

`university.geojson` (214 footprints, 64 KB) outlines the university buildings: OSM buildings with
`amenity=university`, `building=university`, operator Universität Tübingen / Universitätsklinikum
Tübingen, or a name matching the campus patterns in `config/campus.yaml`, within 2.5 km of a campus
site. Each feature has `site` (nearest campus site) and `name`. `MapView.tsx` draws a light fill
below the cells and a hairline above them; the programme's sites get the ink outline and a stronger
fill (F3.4/F4.5). The file is public OSM data, like the basemap, never fetched at runtime from a
third party.

```sh
osmium tags-filter /tmp/basemap/tuebingen.osm.pbf -o /tmp/basemap/buildings.osm.pbf \
  -O w/building w/amenity=university w/operator
osmium export /tmp/basemap/buildings.osm.pbf -f geojsonseq \
  -o /tmp/basemap/buildings.geojsonseq --geometry-types=polygon -a type,id
uv run --package reach-pipeline python web/scripts/make-university.py \
  --input /tmp/basemap/buildings.geojsonseq \
  --output web/public/basemap/university.geojson
```

The live *Wege* (routes) of a listing are not in the basemap: `POST /api/route` returns one
Valhalla walk or bike line, and `MapView.tsx` draws the fastest ones above the cells (F4.5).
