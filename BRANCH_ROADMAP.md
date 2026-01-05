# DAFNI-NIRD Development Roadmap

## Branch Strategy

This repository uses a structured branching approach for incremental development, testing, and optimization.

---

## Current Branches

### 1. **main** (Production Branch)
- **Purpose**: Stable, documented version
- **Contents**: GPU parallelization guide, setup documentation
- **Status**: Ready for review
- **Last Updated**: January 2026

### 2. **setup-nird-baseline-replication** (Current Development)
- **Purpose**: Replicate existing NIRD GB (Great Britain) setup with your data
- **Goals**:
  1. ✅ Verify all dependencies install correctly
  2. ✅ Validate data pipeline works with your NIRD dataset
  3. ✅ Reproduce baseline results (network flows, damage, rerouting)
  4. ✅ Document any configuration adjustments needed
  5. ✅ Create benchmark baseline metrics
  
- **Timeline**: 2-4 weeks
- **Testing Strategy**: Unit tests + integration tests on sample GB data
- **Success Criteria**:
  - All 5 scripts run without errors
  - Outputs match expected schema
  - Performance baseline established
  - Documentation complete

---

## Planned Branches (Future)

### 3. **setup-usa-data-adaptation** (Phase 2)
- **Purpose**: Extend NIRD to USA transportation network
- **Goals**:
  1. Adapt road network ingest for USA OpenStreetMap/TIGER data
  2. Map US road classifications to UK scheme
  3. Validate OD matrix generation for US cities
  4. Run full pipeline on subset (e.g., California network)
  5. Compare results to baseline GB setup

- **Expected Timeline**: 4-6 weeks after Phase 1
- **Dependencies**: Phase 1 complete
- **Branch from**: `setup-nird-baseline-replication`
- **PR to**: `main` with USA methodology documentation

### 4. **parallelize-gpu-optimization** (Phase 3)
- **Purpose**: Implement GPU acceleration and distributed computing
- **Goals**:
  1. Implement CuDF damage calculations (10-30x speedup)
  2. Integrate cuGraph shortest path (20-50x speedup)
  3. Multi-GPU scaling with Dask-CUDA (50-100x speedup)
  4. Distributed sensitivity analysis (20-100x speedup)
  5. Benchmark vs baseline and USA versions

- **Expected Timeline**: 6-8 weeks after Phase 2
- **Dependencies**: Phase 1 & 2 complete
- **Branch from**: `setup-usa-data-adaptation`
- **Hardware Requirements**: GPU access (A100 or RTX 6000)
- **PR to**: `main` with GPU implementation guide

---

## Development Workflow

### Phase 1: Baseline Replication (Current)

```
main
  └── setup-nird-baseline-replication (YOU ARE HERE)
       ├── Verify dependencies & environment
       ├── Test data pipeline with NIRD data
       ├── Run 5-step analysis pipeline
       ├── Create baseline performance metrics
       ├── Document configuration & results
       └── PR → main with results & lessons learned
```

**Current Branch Status**
```bash
Branch: setup-nird-baseline-replication
Commits ahead of main: 0
Status: Ready for data loading and testing
```

### Phase 2: USA Data Adaptation (Future)

```
main
  ├── setup-nird-baseline-replication (COMPLETED)
  └── setup-usa-data-adaptation (CREATE AFTER PHASE 1)
       ├── Adapt network ingest for USA data
       ├── Validate road classification mapping
       ├── Test OD matrix generation
       ├── Run pipeline on sample USA network
       ├── Compare to GB baseline
       └── PR → main with USA methodology
```

### Phase 3: GPU/Parallelization (Future)

```
main
  ├── setup-nird-baseline-replication (COMPLETED)
  ├── setup-usa-data-adaptation (COMPLETED)
  └── parallelize-gpu-optimization (CREATE AFTER PHASE 2)
       ├── Implement GPU damage calculations
       ├── Integrate cuGraph routing
       ├── Multi-GPU with Dask-CUDA
       ├── Distributed sensitivity analysis
       ├── Benchmark all phases
       └── PR → main with GPU guide & results
```

---

## How to Use This Branch

### Getting Started

```bash
# Switch to this branch
git checkout setup-nird-baseline-replication

# Ensure you have NIRD data in the expected location
# (as documented in README.md and SETUP_GUIDE.md)

# Install dependencies
micromamba create -f environment.yaml
micromamba activate nird

# Run tests
python -m pytest tests/

# Execute the 5-step pipeline
python scripts/1_network_flow_model_revision.py 2 8 1
python scripts/2_intersection_analysis.py 30 17
python scripts/3_damage_analysis.py
python scripts/4_rerouting_and_recovery_scenario_loop.py 30 17 1 8
python scripts/5_sensitivity_analysis_direct.py
```

### Documentation to Read First

1. **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - Environment setup and data requirements
2. **[QUICKSTART.md](QUICKSTART.md)** - Running the 5-step pipeline
3. **[GPU_PARALLELIZATION_GUIDE.md](GPU_PARALLELIZATION_GUIDE.md)** - For Phase 3 reference
4. **[README.md](README.md)** - Project overview

---

## Checklist for Phase 1 Completion

### Data & Environment
- [ ] NIRD data downloaded and located correctly
- [ ] Python environment created (`micromamba env create`)
- [ ] All dependencies installed without errors
- [ ] GPU available (optional, but good to have for Phase 3)

### Testing & Validation
- [ ] Run unit tests: `pytest tests/`
- [ ] Script 1 completes (network flow model)
- [ ] Script 2 completes (intersection analysis)
- [ ] Script 3 completes (damage analysis)
- [ ] Script 4 completes (rerouting & recovery)
- [ ] Script 5 completes (sensitivity analysis)

### Results & Documentation
- [ ] All outputs saved to `results/` directory
- [ ] Output schemas validated
- [ ] Performance metrics recorded
- [ ] Any configuration adjustments documented
- [ ] Data issues/quirks noted for future reference

### Before Moving to Phase 2
- [ ] Create branch: `setup-usa-data-adaptation`
- [ ] Document findings in commit message
- [ ] Submit PR to `main` with results
- [ ] Get approval/feedback

---

## Performance Baseline (To Be Filled After Phase 1)

Once you run Phase 1, record these metrics:

```markdown
### GB Baseline (Phase 1) Results

**Hardware**
- CPU: [Your CPU model]
- RAM: [Total RAM]
- GPU: [None / Your GPU model]
- Storage: [SSD/HDD type]

**Execution Times**
- Script 1 (Network Flow Model): ___ minutes
- Script 2 (Intersection Analysis): ___ minutes
- Script 3 (Damage Analysis): ___ minutes
- Script 4 (Rerouting & Recovery): ___ hours
- Script 5 (Sensitivity Analysis): ___ hours
- **Total Pipeline Time**: ___ hours

**Data Sizes**
- Road network nodes: ___ count
- Road network edges: ___ count
- OD pairs: ___ count
- Flood scenarios: ___ count
- Output size: ___ GB

**Key Issues/Learnings**
- [Issue 1]: [Solution or workaround]
- [Issue 2]: [Solution or workaround]
- Performance bottleneck: [Specific operation]
```

---

## Tips for This Branch

### Memory Management
- If you run out of RAM, use `chunked_processing=True` in scripts
- Monitor memory with: `python -m memory_profiler script.py`

### Debugging
- Set `logging.basicConfig(level=logging.DEBUG)` to get verbose output
- Use `breakpoint()` to step through problem areas
- Save intermediate results to CSV for inspection

### Performance Monitoring
- Use `cProfile` to identify slowest functions:
  ```bash
  python -m cProfile -s cumtime scripts/1_network_flow_model_revision.py
  ```

### Troubleshooting
- Check [SETUP_GUIDE.md](SETUP_GUIDE.md) for common issues
- Verify data paths in `load_config()` match your setup
- Ensure parquet files are readable: `geopandas.read_parquet(path)`

---

## Next Steps

### Immediate (This Week)
1. [ ] Verify NIRD data is accessible locally
2. [ ] Confirm environment setup works
3. [ ] Run 1-2 scripts to validate pipeline

### Short Term (This Month)
1. [ ] Complete all 5 scripts on full dataset
2. [ ] Collect baseline performance metrics
3. [ ] Document any issues encountered
4. [ ] Prepare PR to main branch

### Medium Term (Next Month)
1. [ ] Create `setup-usa-data-adaptation` branch
2. [ ] Start USA data pipeline adaptation
3. [ ] Plan GPU optimization approach

---

## Resources

- **Docs**: See [GPU_PARALLELIZATION_GUIDE.md](GPU_PARALLELIZATION_GUIDE.md) for optimization references
- **Issues**: Create GitHub issues if you hit blockers
- **Questions**: Reach out to @edwardoughton or NISMOD team

---

## Branch Protection Rules

Once Phase 1 completes, consider protecting `main` branch:
- Require PR reviews before merge
- Require passing CI/CD tests
- Require up-to-date branches
- Dismiss stale pull request approvals

This ensures quality on main while allowing experimental work in feature branches.

---

**Branch Created**: January 2026  
**Status**: Active Development  
**Phase**: 1 of 3
