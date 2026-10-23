# Phase 2 progress log

Plain-English summary after each phase-2 step (steps 10-20). Numbers trace to `outputs/tables/`; specifications
were pre-registered in `outputs/decisions.md` (items 97 onwards) before each step was run.

## Data (23 Oct 2026)

- Fetched URA MP2019 subzones (332) and land use (113,213 polygons), Census 2020 residents by subzone and age
  (SingStat's 2025 subzone tables were not downloadable: 404), HDB property information and resale prices,
  private transactions 2020-2025 from the earlier repo (SHA-256 checked; 2,298 projects with coordinates),
  data.gov.sg hotels / tourist attractions / hawker centres / LTA bus stops, NEA 24-hour forecasts (14,458 issues,
  Oct 2021 - Sep 2026).
- The public OpenStreetMap Overpass servers timed out or refused requests, so destinations (16,093 named features,
  incl. 522 OSM taxi points) and the drivable road network (332k nodes) come from the Geofabrik extract, parsed
  locally. LTA pick-up bays need a DataMall key we do not have; OSM taxi points are a partial proxy.
