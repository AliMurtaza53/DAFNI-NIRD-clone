I am building a Python transportation network hazard-disruption model. The network analysis/assignment component is already functional. I now want to add a freight OD disaggregation module inspired by the FAF5 Highway Network Assignment Model workflow from FHWA.

Relevant FHWA FAF5 workflow:
1. FAF5 commodity flows are disaggregated from 132 FAF zones to a more granular geography such as counties, sub-county areas, ports, airports, and border crossings.
2. Disaggregated commodity tonnage is converted to truck trips using payload factors by commodity group, length of haul, and truck type.
3. Truck trips are assigned to a national highway network using route choice/path enumeration.

For my project, I only need to implement Steps 1 and 2 as a preprocessing module because the network assignment component already works.

Goal:
Create a Python module that converts FAF5 zone-to-zone commodity flows into county/subcounty-level truck OD matrices that can be passed into my existing network assignment pipeline.

Desired module name:
freight_od_disaggregation.py

Inputs:
- FAF5 OD flow table with origin FAF zone, destination FAF zone, commodity group, mode, tons, value, year
- FAF zone to county/subcounty crosswalk
- County/subcounty production and attraction weights by commodity group
- County/subcounty centroid coordinates
- Payload factor table by commodity group, truck type, and possibly distance bin
- Optional distance matrix or network skim

Outputs:
- county/subcounty OD commodity tonnage table
- county/subcounty truck trip OD table
- optional daily truck trip matrix by truck type and commodity
- diagnostics showing preservation of FAF zone totals

Implementation requirements:
- Use pandas/geopandas/numpy where needed
- Keep the module independent of the assignment engine
- Include functions for:
  1. loading input tables
  2. computing production/attraction weights
  3. applying gravity-based disaggregation within each FAF OD pair and commodity
  4. balancing results to preserve FAF OD totals
  5. converting tons to truck trips using payload factors
  6. exporting OD tables for assignment
  7. producing validation summaries
- Include clear docstrings and type hints
- Design the code so it can be run for Virginia first, then scaled to CONUS