# Administrative Boundaries Data

This directory contains US administrative boundary data (states, counties, cities) and DMV-specific Traffic Analysis Zones (TAZ) for use in spatial analysis.

## Downloaded Data

### Successfully Downloaded ✅

#### 1. **US States** (tl_2024_us_state.*)
- **Source**: US Census Bureau TIGER/Line 2024
- **Records**: 56 (includes territories)
- **Format**: Shapefile
- **CRS**: EPSG:4269 (NAD83)
- **Use**: Regional boundary mapping, state-level aggregation

#### 2. **US Counties** (tl_2024_us_county.*)
- **Source**: US Census Bureau TIGER/Line 2024
- **Records**: 3,233 counties nationwide
- **Format**: Shapefile
- **CRS**: EPSG:4269 (NAD83)
- **Use**: County-level analysis

#### 3. **DMV Counties** (DMV_counties.gpkg)
- **Records**: 213 counties (filtered from national dataset)
- **Coverage**: Virginia (133) + Maryland (24) + West Virginia (55) + DC (1)
- **Format**: GeoPackage
- **CRS**: EPSG:4269 (NAD83)
- **Use**: DMV regional analysis, direct regional filtering
- **Key Columns**: NAME, STATEFP, GEOID, STATE (custom)

#### 4. **US Cities/Places** (tl_2024_us_place.* - if download succeeded)
- **Source**: US Census Bureau TIGER/Line 2024
- **Records**: ~28,000+ incorporated places, CDPs nationwide
- **Format**: Shapefile
- **CRS**: EPSG:4269 (NAD83)
- **Use**: City-level boundary mapping, urban area identification

### Requires Manual Download ⚠️

#### 5. **DMV Traffic Analysis Zones - TAZ** (TAZ_DMV.gpkg - NOT YET PRESENT)
- **Source**: Metropolitan Washington Council of Governments (MWCOG)
- **Purpose**: Traffic analysis zone definitions for demand modeling
- **Format**: FileGDB (requires conversion to GeoPackage)
- **CRS**: Typically EPSG:4269 or project-specific
- **Download Instructions**:
  1. Visit: https://hub.mwcog.org
  2. Search for "Traffic Analysis Zone" or "TAZ"
  3. Download FileGDB or Shapefile
  4. Convert to GeoPackage using:
     ```bash
     ogr2ogr -f GPKG TAZ_DMV.gpkg /path/to/MWCOG.gdb TAZ
     ```
  5. Place converted file in this directory

## Usage Examples

### Load DMV Counties
```python
import geopandas as gpd
counties_dmv = gpd.read_file('DMV_counties.gpkg')
print(f"DMV Coverage: {counties_dmv['STATE'].unique()}")
```

### Filter to Fairfax County
```python
fairfax = counties_dmv[counties_dmv['NAME'] == 'Fairfax']
```

### Load all US States
```python
states = gpd.read_file('tl_2024_us_state.shp')
```

### Load TAZ (once downloaded and converted)
```python
taz = gpd.read_file('TAZ_DMV.gpkg')
print(f"Total TAZs: {len(taz)}")
```

## Data Dictionary - DMV_counties.gpkg

| Column | Type | Description |
|--------|------|-------------|
| NAME | string | County name |
| STATEFP | string | State FIPS code (01=50 states, 11=DC) |
| GEOID | string | County GEOID (STATEFP + COUNTYFP) |
| STATE | string | State abbreviation (VA, MD, WV, DC) |
| geometry | geometry | County boundary polygon (EPSG:4269) |

## CRS Notes

All downloaded Census TIGER/Line data uses **EPSG:4269 (NAD83)** by default.

For ArcGIS Pro or mapping, you may want to reproject to:
- **EPSG:3857** (Web Mercator) for web mapping
- **EPSG:4326** (WGS84) for universal compatibility
- **EPSG:2926** or region-specific State Plane Coordinates for precise local analysis

Example conversion:
```python
counties_dmv_3857 = counties_dmv.to_crs('EPSG:3857')
counties_dmv_3857.to_file('DMV_counties_3857.gpkg', driver='GPKG')
```

## Related Files in Sandbox

- `../networks/faf5/` - FAF5 road network data (clipped to study area)
- `../` - Clipped Fairfax study area and OD matrices
- `study_area/` - Fairfax study area boundary definition

## License & Attribution

- **TIGER/Line Data**: Public domain, US Census Bureau
- **MWCOG TAZ Data**: Check MWCOG licensing terms
- **County Names & Boundaries**: Public domain

## Last Updated

- States: 2024-03-30 (TIGER/Line 2024)
- Counties: 2024-03-30 (TIGER/Line 2024)
- Cities: 2024-03-30 (TIGER/Line 2024, if downloaded)
- TAZ: Pending manual download from MWCOG
