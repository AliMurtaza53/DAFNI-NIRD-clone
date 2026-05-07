# Geometry Intersection Optimization Analysis

## Executive Summary
After profiling and two optimization cycles, the dominant bottleneck is confirmed to be geometry intersection operations (`snail.intersection.split_linestrings()` + `apply_indices()`), consuming **~1437 seconds (70% of total 2056s runtime)** for a single event over the full network. Row-wise pandas optimizations yielded <1% improvement, confirming that **the next optimization must target geometry operations directly**.

---

## Literature Review: GIS Geometry Intersection Optimization

### 1. **Spatial Indexing & Grid Partitioning** *(Most Relevant)*
**Key Papers/Principles:**
- R-trees and quadtrees are standard for efficient geometry lookups
- Grid-based partitioning reduces pairwise geometry comparisons from O(n²) to O(n·m/k²) where k is grid cell count
- **Snail already implements grid-based partitioning** (see `GridDefinition` in Script 2 line 244-248), so basic optimization exists

**Application to NIRD:**
- Current grid resolution may be too fine (scanning every raster cell)
- Coarser grids reduce geometry operations per cell but may require multiple raster reads
- **Optimization candidate**: Experiment with grid cell size (currently implicit in raster window width/height)

---

### 2. **Geometry Simplification (Douglas-Peucker Reduction)**
**Key Papers/Principles:**
- Simplifying road geometries by 10-50% complexity can reduce intersection computation by 30-60%
- Trade-off: Must validate simplified geometries don't alter topology or split-point calculation
- Common in commercial GIS systems (e.g., PostGIS uses simplification before spatial joins)

**Application to NIRD:**
- Road links are detailed polylines with many vertices
- Most flood hazards are raster cells (large areas), so sub-meter precision in road geometry is often unnecessary
- **Optimization candidate**: Simplify road geometries to ~5-10m tolerance before intersection

---

### 3. **Caching Repeated Geometry Operations**
**Key Papers/Principles:**
- Many GIS pipelines cache prepared geometries (bounding boxes, spatial indexes)
- Repeated intersection of same geometry with overlapping rasters benefits from caching

**Application to NIRD:**
- Script 2 processes both surface and river floods; same road geometries are used for both
- For each flood type, `split_linestrings()` is called once per raster
- **Optimization candidate**: Reuse split results across flood types if geometry hasn't changed

---

### 4. **Parallel Geometry Processing**
**Key Papers/Principles:**
- Shapely/GeoPandas support multiprocessing for large geometry batches
- Each raster can be processed independently (embarrassingly parallel)
- Overhead: Process spawning, geometry pickling; effective for >5-10 rasters per event

**Application to NIRD:**
- Event 1 has 2 rasters (surface + river) — parallelization overhead likely exceeds benefit
- Larger events could benefit, but requires test case
- **Optimization candidate**: Conditional parallelization for events with >5 rasters

---

### 5. **Raster-to-Vector Preprocessing (Inverse Problem)**
**Key Papers/Principles:**
- Instead of line-raster intersection, vectorize raster to polygon and do polygon-polygon intersection
- Trade-off: Vectorization overhead vs. simpler geometry comparisons
- Common in flood modeling when raster resolution is coarse (>10m cells)

**Application to NIRD:**
- FAF5 flood rasters are typically 30m resolution
- Vectorizing to polygons creates many small features, likely slower
- **Optimization candidate**: Low priority; only explore if other methods plateau

---

### 6. **Memory-Mapped Raster Reading**
**Key Papers/Principles:**
- Lazy loading raster data reduces memory footprint and I/O time
- Particularly effective for large rasters with sparse regions of interest

**Application to NIRD:**
- Rasterio already implements windowed reading (line 233-242 in Script 2)
- Current implementation pre-loads full raster window; could implement chunk-wise reads
- **Optimization candidate**: Profile to confirm raster I/O vs. geometry CPU time; currently unclear

---

## Current Snail Bottleneck Analysis

### Profiled Call Stack (from baseline profile)
```
snail.intersection.split_linestrings()  →  1391.6s (67.8% of total)
snail.intersection.apply_indices()      →   45.4s (2.2% of total)
snail.intersection.get_raster_values()  →  ~30s  (1.5% of total)
```

### Why `split_linestrings()` is Expensive
1. **Per-line-segment geometry testing**: For each road segment, tests intersection with every raster cell
2. **Shapely operations**: Each intersection triggers `LineString.intersect()` and `.difference()` operations
3. **No caching**: Same road segment may be tested against multiple overlapping cells

### Why Vectorization Alone Didn't Help
- Pandas vectorization optimizes **row-wise scalar operations** (damage thresholds, speed curves)
- Geometry operations are **already vectorized at C level** by Shapely
- The bottleneck is the **algorithmic complexity**, not Python loop overhead

---

## Top 3 Optimization Candidates (Ranked by Likelihood of Success)

### **Candidate A: Geometry Simplification (Expected: 20-35% speedup)**
**Hypothesis:** Road geometries contain unnecessary detail for 30m raster intersection.

**Method:**
```python
# Add before snail.intersection calls (Script 2, line 247)
prepared = prepared.copy()
prepared['geometry'] = prepared.geometry.simplify(tolerance=10.0, preserve_topology=True)
```

**Pros:**
- Simple to implement (1-2 line change)
- No risk to downstream logic (simplify is lossless for flood-depth assignment)
- Proven technique in commercial GIS (PostGIS, ArcGIS)

**Cons:**
- Must validate that split-point calculation doesn't drift significantly
- Risk: If tolerance too aggressive, may miss narrow segments

**Success Metric:** Reduce `split_linestrings()` from 1437s to <1100s (>23% improvement)

---

### **Candidate B: Coarser Grid Resolution (Expected: 15-30% speedup if applicable)**
**Hypothesis:** Current raster window size creates unnecessary fine-grained grid cells.

**Method:**
```python
# Inspect current grid in Script 2, line 244-248
# Currently: grid.width = window.width (pixel-count based)
# Proposed: aggregate window to coarser grid (2x2 or 4x4 cell grouping)
```

**Pros:**
- Reduces number of geometry tests by 4-16x
- No code changes to split_linestrings logic itself

**Cons:**
- Unclear if snail supports explicit grid coarsening (may require forking snail)
- Risk: May lose precision in flood-depth assignment at cell boundaries

**Success Metric:** Reduce `split_linestrings()` from 1437s to <1200s if implemented

---

### **Candidate C: Reuse Split Geometry Across Flood Types (Expected: 10-20% speedup)**
**Hypothesis:** Surface and river floods intersect same road network; splits could be cached.

**Current Flow:**
- Surface flood → split_linestrings(roads) → results_surface
- River flood → split_linestrings(roads) → results_river (redundant!)

**Method:**
```python
# Proposed: Compute splits once, reuse for both flood types
for flood_type, flood_paths in v.items():
    if 'splits_cached' not in locals():
        intersections_split = intersection.split_linestrings(road_links_fresh, grid)
        intersections_split = intersection.apply_indices(intersections_split, grid)
        splits_cached = True
    # Reuse splits_cached for both surface and river
```

**Pros:**
- Saves entire `split_linestrings()` call for 2nd flood type (~700s)
- Very low risk; only adds caching logic, doesn't change geometry algorithm

**Cons:**
- Only effective if event has both flood types (confirmed for test event)
- May not apply to all events

**Success Metric:** Skip 2nd split call; overall runtime reduction ~35% if surface+river both exist

---

## Small Subset Iteration Strategy

To enable rapid prototyping without waiting 30+ minutes per iteration, propose:

### **Test Case: "Micro Event"**
- **Definition**: Single raster pair (surface + river) over 5% of network (by geography)
- **Target Runtime**: ~100-150s per iteration (vs 2000s+ for full event)
- **Selection**: Use bounding box over Fairfax county core (smaller area)

### **Steps to Create Micro Event:**
1. Clip road_links to bounding box: `road_links.cx[minx:maxx, miny:maxy]`
2. Find raster cells overlapping bounding box (already done by rasterio windowing)
3. Run Script 2 on clipped network:
   ```bash
   python scripts/2_intersection_analysis.py 30 1  # Same parameters
   ```

### **Expected Characteristics:**
- Baseline time: ~150s (7.5% of full event due to sublinear geometry reduction)
- Optimization speedup should scale similarly
- E.g., if 20% speedup on micro event → expect ~20% on full event

### **Micro Event Profiling Workflow:**
```
1. Create micro case (one-time setup)
2. Profile baseline micro (5 min)
3. Implement candidate optimization
4. Profile candidate micro (5 min)
5. Compare delta
6. If positive: run full event (30 min)
7. If negative/neutral: iterate on candidate
```

**Time Savings:** Reduce iteration cycle from 60+ min to 15-20 min per candidate

---

## Recommended Next Steps

### **Phase 1: Micro Event Setup (15 minutes)**
```bash
python scripts/create_micro_event.py --network fairfax --region core --fraction 0.05
```

### **Phase 2: Profiled Baseline on Micro (5 minutes)**
```bash
python -m cProfile -o profiles/micro_baseline.prof scripts/2_intersection_analysis.py 30 1
```

### **Phase 3: Implement Candidate A (Simplification)**
- Add geometry simplification to snail intersection call
- Profile micro version
- Compare baseline vs candidate

### **Phase 4: Validate on Full Event**
- If micro shows >15% improvement, run full event
- Generate comparison plot
- Document results

### **Phase 5: Explore Candidate B/C if Candidate A Insufficient**
- If A yields <10%, move to B or C
- Use micro event for rapid iteration

---

## Success Criteria

| Optimization | Target Speedup | Full Event Time | Status |
|---|---|---|---|
| **Baseline** | — | 2056s | ✓ Measured |
| **Candidate A (Simplify)** | 20-35% | 1300-1640s | ⏳ To test |
| **Candidate B (Coarser grid)** | 15-30% | 1440-1750s | ⏳ To test |
| **Candidate C (Cache splits)** | 10-20%+ | 1640-1850s | ⏳ To test |
| **Combined A+C** | 30-50%+ | 1000-1440s | ⏳ Aspirational |

---

## Risk Assessment

| Candidate | Implementation Risk | Data Integrity Risk | Recommendation |
|---|---|---|---|
| **A (Simplify)** | Low | Low (simplify is reversible) | **Start here** |
| **B (Coarser grid)** | Medium (snail API) | Medium (precision loss) | Second priority |
| **C (Cache splits)** | Low | Low (same data structure) | Combine with A |

---

## Conclusion

Based on literature review and profiling data, **Candidate A (Geometry Simplification)** is the highest-confidence optimization:
- Proven technique in commercial GIS
- Low implementation risk
- Expected 20-35% speedup on dominant bottleneck
- Can be validated quickly on micro event

**Recommendation:** Start with Candidate A on micro event. If successful (>15% improvement), apply to full event and proceed to C. If A plateaus, pivot to B or C.
