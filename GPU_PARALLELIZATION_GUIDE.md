# GPU Cluster & Parallelization Guide for DAFNI-NIRD

A comprehensive guide to understanding GPU acceleration opportunities and scaling strategies for the National Infrastructure Resilience Demonstrator (NIRD) codebase.

## Overview

Based on analysis of the DAFNI-NIRD codebase and the hazard paper methodology, this guide identifies computational bottlenecks and provides practical pathways to GPU-accelerated and distributed computing.

---

## Current Computational Bottlenecks

### 1. Network Flow Simulation
- **Location**: [src/nird/road_revised.py](src/nird/road_revised.py)
- **Workload**: Shortest path calculations and traffic flow modeling using `igraph`
- **Characteristics**: CPU-bound, integer linear programming
- **Scale**: Processes millions of OD pairs across GB road network

### 2. Damage Analysis
- **Location**: [scripts/3_damage_analysis.py](scripts/3_damage_analysis.py)
- **Workload**: Row-wise damage calculations on GeoDataFrames (100K+ road segments)
- **Operation**: Flood depth → damage fraction → damage cost (piecewise linear functions)
- **Characteristics**: Highly parallelizable, GPU-friendly operations

### 3. Rerouting & Recovery Simulation
- **Location**: [scripts/4_rerouting_and_recovery_scenario_loop.py](scripts/4_rerouting_and_recovery_scenario_loop.py)
- **Workload**: Multi-day recovery scenarios with repeated routing operations
- **Characteristics**: Embarrassingly parallel across days and scenarios
- **Scale**: 111+ days × multiple flood events

### 4. Sensitivity Analysis
- **Location**: [scripts/5_sensitivity_analysis_direct.py](scripts/5_sensitivity_analysis_direct.py)
- **Workload**: Morris sensitivity analysis across parameter space
- **Characteristics**: Massive scenario enumeration (Morris screening generates N*(D+1) samples)
- **Advantage for GPU**: Perfect use case for batch processing

---

## GPU Acceleration Opportunities

### Priority Matrix

| Workload | GPU Potential | Effort | Speedup | Priority |
|----------|---------------|--------|---------|----------|
| **Network Routing** | Very High | Medium | 10-100x | **HIGH** |
| **Damage Calculations** | Very High | Low | 5-50x | **HIGH** |
| **Sensitivity Analysis** | High | Medium | 20-100x | **MEDIUM-HIGH** |
| **Geospatial Operations** | Medium | High | 10-30x | **MEDIUM** |

---

## Detailed Opportunity Analysis

### 1. Network Analysis & Shortest Path (HIGH PRIORITY)

**Current Implementation**
```python
# Uses igraph for routing (CPU-bound)
network, road_links = func.create_igraph_network(road_links)
road_links, isolation, odpfc, _ = func.network_flow_model(
    road_links,
    network,
    od_node_2021,
    flow_breakpoint_dict,
    num_of_chunk,
    num_of_cpu,
    db_path,
)
```

**GPU Solution: cuGraph**
- **Technology**: [NVIDIA RAPIDS cuGraph](https://rapids.ai/cugraph/)
- **Capabilities**: GPU-accelerated shortest path, betweenness centrality, pagerank
- **Speedup**: 10-100x for large networks
- **Integration Effort**: Medium (requires algorithm changes)
- **Best For**: Million+ node networks

**Alternative: Numba + Dijkstra**
- JIT compilation to GPU for custom routing algorithms
- More flexible than cuGraph
- Steeper learning curve

---

### 2. Damage Calculations (MEDIUM-HIGH PRIORITY)

**Current Implementation**
```python
# Row-wise pandas operations
disrupted_links["damage_level_max"] = disrupted_links.apply(
    lambda row: compute_damage_level(row["flood_type"], row["road_classification"]),
    axis=1
)
```

**GPU Solutions**

#### Option A: CuDF (Easiest)
```python
import cudf
df_gpu = cudf.from_pandas(disrupted_links)
# Vectorized operations on GPU
df_gpu["damage"] = df_gpu["flood_depth"].apply(damage_func)
```
- **Speedup**: 5-30x
- **Effort**: Low (minimal code changes)
- **Best For**: Large DataFrames, simple vectorizable operations

#### Option B: Dask-CUDA (Most Scalable)
```python
import dask_cuda
from dask_cuda import LocalCUDACluster
from dask.distributed import Client

cluster = LocalCUDACluster(n_workers=4)
client = Client(cluster)
ddf = dask.dataframe.from_pandas(df, npartitions=16)
result = ddf.apply(damage_function).compute()
```
- **Speedup**: 30-100x with 4+ GPUs
- **Effort**: Medium
- **Best For**: Multi-GPU systems, large datasets

#### Option C: Numba CUDA (Fastest, Most Complex)
```python
from numba import cuda
import numpy as np

@cuda.jit
def gpu_damage_kernel(flood_depth, output):
    idx = cuda.grid(1)
    if idx < len(flood_depth):
        output[idx] = piecewise_linear_damage(flood_depth[idx])

# Transfer to GPU and execute
gpu_damage_kernel[blocks, threads](gpu_depth_array, gpu_output_array)
```
- **Speedup**: 50-200x
- **Effort**: High (requires code rewrite)
- **Best For**: Complex vectorized math operations

**Recommendation**: Start with **CuDF** for quick wins, then migrate to **Dask-CUDA** for multi-GPU scaling.

---

### 3. Sensitivity Analysis (MEDIUM PRIORITY)

**Current Implementation**
```python
# Morris sensitivity analysis
from SALib.analyze import morris

morris_results = morris.analyze(
    problem, inputs, outputs
)
```

**GPU Acceleration Strategy**

The Morris method involves:
1. **Sampling** (N×(D+1) samples generation) ← **Parallelizable**
2. **Model Evaluation** (embarrassingly parallel) ← **GPU target**
3. **Analysis** (statistical aggregation) → Small, CPU OK

```python
# Parallelize OD evaluation with Dask-CUDA
sensitivity_samples = generate_morris_samples(problem)

def evaluate_network(params):
    """Evaluate network with given parameters"""
    return run_traffic_simulation(network, params)

# Distribute across GPUs
results = dask.bag.from_sequence(sensitivity_samples).map(
    evaluate_network
).compute()
```

**Potential Speedup**: 20-100x with GPU batch processing

---

### 4. Geospatial Operations (MEDIUM PRIORITY)

**Current Implementation**
```python
# Raster-vector intersection with geopandas + snail
intersections = intersection.intersect_features(flood_raster, road_links)
```

**GPU Solution Options**

1. **cuGIS (Experimental)** - NVIDIA's experimental GPU-accelerated GIS
   - Status: Early stage, limited functionality
   - Speedup: 10-30x for intersection operations

2. **Preprocessing Strategy** (Recommended)
   - Pre-index geospatial data on GPU
   - Cache spatial indices in GPU memory
   - Fall back to CPU for complex operations
   - **Realistic Speedup**: 5-10x with careful implementation

3. **Batch Processing**
   - Process multiple flood events simultaneously on GPU
   - Amortize data transfer costs
   - **Practical Speedup**: 5-20x

**Recommendation**: Focus on **batch processing** for near-term gains while GPU GIS tools mature.

---

## Learning Resources & Technology Stack

### Essential References

#### Official Documentation (Start Here)
1. **[RAPIDS Documentation](https://docs.rapids.ai/)**
   - cuDF (GPU DataFrames)
   - cuGraph (GPU graph algorithms)
   - cuML (GPU machine learning)
   - **Estimated Reading Time**: 4-6 hours

2. **[Dask Documentation](https://docs.dask.org/)**
   - Task scheduling and distributed computing
   - Multi-GPU orchestration with Dask-CUDA
   - **Estimated Reading Time**: 3-4 hours

3. **[Dask-CUDA](https://docs.rapids.ai/api/dask-cuda/)**
   - GPU cluster coordination
   - Multi-GPU, multi-node scaling
   - **Estimated Reading Time**: 2-3 hours

4. **[Numba CUDA Documentation](https://numba.readthedocs.io/en/stable/cuda/)**
   - JIT compilation to GPU
   - Custom kernel development
   - **Estimated Reading Time**: 5-8 hours (if using)

#### Books & Courses

| Resource | Focus | Time | Level |
|----------|-------|------|-------|
| *High Performance Python* (Gorelick & Ozsvald) | Profiling, optimization fundamentals | 2 weeks | Intermediate |
| *Distributed Machine Learning Patterns* | Distributed computing design patterns | 3 weeks | Advanced |
| NVIDIA DLI Courses | GPU computing foundations | 1-2 weeks | Beginner |
| Coursera - Parallel Programming | CUDA fundamentals | 4-6 weeks | Intermediate |

#### Key Papers & Blog Posts
- [RAPIDS Blog: Accelerating Python Data Science](https://rapids.ai/blog/)
- [Dask: Parallel Computing with Python](https://arxiv.org/pdf/1810.02534.pdf)
- [cuGraph: GPU-Accelerated Graph Analytics](https://arxiv.org/pdf/1906.04589.pdf)

---

## Recommended Learning Path

### Phase 1: Profiling & Baseline (1 week)

**Objective**: Identify actual bottlenecks with data

**Tasks**:
1. Profile current code with `cProfile` and `line_profiler`
   ```bash
   pip install line_profiler memory_profiler
   python -m cProfile -s cumtime scripts/1_network_flow_model_revision.py > profile.txt
   kernprof -l -v scripts/1_network_flow_model_revision.py
   ```

2. Measure computational time breakdown:
   - Network initialization
   - Shortest path routing
   - Damage calculation
   - I/O operations

3. Estimate GPU memory requirements:
   - Network size in memory
   - GeoDataFrame sizes
   - OD matrix size

4. **Deliverable**: Profiling report with top 5 bottlenecks

**Learning**: 2-3 hours documentation reading

---

### Phase 2: CPU Parallelization Optimization (1-2 weeks)

**Objective**: Maximize CPU utilization before GPU investment

**Current State**: Uses `multiprocessing.Pool` (basic)

**Improvements**:
1. **Switch to Dask for better task scheduling**
   ```python
   # Before: Basic multiprocessing
   with Pool(num_of_cpu) as pool:
       results = pool.map(process_od_chunk, chunks)
   
   # After: Dask with smarter scheduling
   import dask
   results = dask.compute(*[
       dask.delayed(process_od_chunk)(chunk) 
       for chunk in chunks
   ])
   ```

2. **Optimize I/O with Parquet format** (already using)
   - Verify compression settings
   - Use column selection for partial reads

3. **Profile memory usage**
   - Reduce peak memory with lazy loading
   - Use chunked processing for large datasets

**Learning**: 1-2 hours (Dask tutorials)

**Expected Gain**: 2-4x speedup from better parallelization

---

### Phase 3: GPU Piloting (2-4 weeks)

**Objective**: Validate GPU acceleration on realistic workload

**Step 1: Damage Calculation Pilot** (Easiest)
```python
# Test cuDF on damage analysis
import cudf

# Select 10% of data for testing
sample_links = disrupted_links.sample(frac=0.1)

# CPU baseline
import time
start = time.time()
cpu_result = sample_links.apply(calculate_damage_row, axis=1)
cpu_time = time.time() - start

# GPU version
df_gpu = cudf.from_pandas(sample_links)
start = time.time()
gpu_result = df_gpu.apply(calculate_damage_row).to_pandas()
gpu_time = time.time() - start

print(f"Speedup: {cpu_time / gpu_time:.1f}x")
```

**Step 2: cuGraph Shortest Path Pilot**
```python
import cugraph as cg

# Convert to cuGraph format
cuG = cg.from_pandas_edgelist(
    road_links[['from_id', 'to_id', 'length']],
    source='from_id', target='to_id', edge_attr='length'
)

# Compare shortest paths
# Baseline: igraph
# GPU: cuGraph
```

**Step 3: Document Results**
- Actual vs. expected speedup
- GPU memory usage
- Data transfer overhead
- Optimal batch sizes

**Deliverable**: Pilot report with measured speedups

---

### Phase 4: Full-Scale Integration (3-6 weeks)

**Objective**: Deploy GPU acceleration across entire pipeline

#### Stage 4A: Single-GPU Optimization
- Replace CPU damage calculations with cuDF
- Implement GPU-accelerated routing with cuGraph
- Optimize batch sizes and memory management
- **Expected Speedup**: 10-50x

#### Stage 4B: Multi-GPU Scaling
```python
# Distributed damage calculation across GPUs
from dask_cuda import LocalCUDACluster
from dask.distributed import Client

cluster = LocalCUDACluster(n_workers=4, memory_limit='40GB')
client = Client(cluster)

# Process each scenario on different GPU
results = {}
for scenario_id in scenarios:
    future = client.submit(
        process_scenario_gpu,
        scenario_data,
        workers=[f'tcp://gpu-{i % 4}']
    )
    results[scenario_id] = future
```
- **Expected Speedup**: 20-100x with 4+ GPUs

#### Stage 4C: Multi-Node Deployment
- Deploy on Kubernetes cluster
- Use Ray Cluster for distributed task scheduling
- Implement automatic GPU memory management
- **Expected Speedup**: 50-200x with 16+ GPUs across 4+ nodes

---

## Technology Recommendation by Use Case

| Use Case | Technology | Effort | Speedup | Recommended |
|----------|-----------|--------|---------|-------------|
| Damage calculations | **CuDF** | Low | 5-30x | ✅ Start here |
| Network routing | **cuGraph** | Medium | 10-100x | ✅ After damage |
| Sensitivity analysis | **Dask-CUDA** | Medium | 20-100x | ✅ Phase 4 |
| Custom math kernels | **Numba CUDA** | High | 50-200x | ⚠️ Only if needed |
| Geospatial operations | **Batch processing** | Medium | 5-20x | ⏸️ When cuGIS matures |

---

## Practical Code Examples

### Example 1: Damage Calculation with CuDF

**Before (CPU)**
```python
disrupted_links["C1_damage"] = disrupted_links.apply(
    lambda row: damage_curves["C1"].damage_fraction(row["flood_depth"]),
    axis=1
)
```

**After (GPU with CuDF)**
```python
import cudf

# Transfer to GPU
df_gpu = cudf.from_pandas(disrupted_links)

# Vectorized GPU computation (much faster)
damage_values_gpu = cudf.concat([
    df_gpu["flood_depth"].map_partitions(
        lambda x: x.apply(lambda d: damage_curves[curve].damage_fraction(d))
    )
    for curve in ["C1", "C2", "C3", "C4", "C5", "C6"]
], axis=1)

# Transfer results back
disrupted_links = damage_values_gpu.to_pandas()
```

**Performance**: 10-30x faster

---

### Example 2: OD Pair Processing with Dask-CUDA

**Before (Single CPU)**
```python
def process_od_chunk(chunk):
    return func.network_flow_model(
        road_links, network, chunk, params
    )

with Pool(8) as pool:
    results = pool.map(process_od_chunk, od_chunks)
```

**After (Multi-GPU)**
```python
from dask_cuda import LocalCUDACluster
from dask.distributed import Client, as_completed
import dask

cluster = LocalCUDACluster(n_workers=4, memory_limit='40GB')
client = Client(cluster)

futures = []
for chunk in od_chunks:
    future = client.submit(
        process_od_chunk_gpu,
        chunk,
        road_links_gpu,
        network_gpu
    )
    futures.append(future)

results = [f.result() for f in as_completed(futures)]
```

**Performance**: 30-100x faster with 4 GPUs

---

### Example 3: Sensitivity Analysis with GPU Batch Processing

**Before (Serial)**
```python
for params in sensitivity_samples:
    result = run_traffic_simulation(network, params)
    results.append(result)
```

**After (GPU-accelerated with batching)**
```python
from functools import partial

def batch_evaluate(params_batch):
    """Evaluate multiple parameter sets on GPU"""
    return [run_traffic_simulation_gpu(network, p) for p in params_batch]

# Process in batches
batch_size = 128
batches = [sensitivity_samples[i:i+batch_size] 
           for i in range(0, len(sensitivity_samples), batch_size)]

results = []
for batch in batches:
    batch_results = batch_evaluate(batch)
    results.extend(batch_results)
```

**Performance**: 20-100x faster depending on batch size and GPU count

---

## Infrastructure Requirements

### Hardware Recommendations

#### Single Node GPU
- **GPU**: 1× NVIDIA A100 (80GB) or 2× RTX 6000 Ada
- **CPU**: 32+ cores (AMD Threadripper or Intel Xeon)
- **RAM**: 256-512 GB
- **Storage**: 2-4 TB NVMe SSD
- **Cost**: $50K-100K
- **Best For**: Prototyping and small-scale scenarios

#### Multi-GPU Server
- **GPUs**: 4× NVIDIA A100 (80GB) with NVLink
- **CPU**: 64+ cores (AMD EPYC or Intel Xeon)
- **RAM**: 512 GB+
- **Storage**: 8-16 TB NVMe SSD
- **Cost**: $150K-300K
- **Best For**: Production sensitivity analysis

#### Kubernetes Cluster
- **Nodes**: 4-16 GPU nodes with 4× A100 each
- **Network**: High-bandwidth interconnect (100 Gbps)
- **Storage**: Shared NVMe storage (Ceph or NAS)
- **Orchestration**: Kubernetes + RAPIDS operator
- **Cost**: $500K-2M depending on scale
- **Best For**: Large-scale distributed scenarios

### Software Stack

```
GPU Compute:
├── NVIDIA CUDA Toolkit (11.8+)
├── cuDNN (GPU neural network library)
└── NCCL (GPU collective communications)

Data Science:
├── RAPIDS (cuDF, cuGraph, cuML)
├── Dask-CUDA (multi-GPU coordination)
├── NumPy/Pandas (fallback for CPU ops)
└── PyArrow (efficient data format)

Geospatial:
├── GeoPandas (CPU fallback)
├── Shapely (CPU geometry ops)
├── GDAL (raster processing)
└── cuGIS (GPU GIS - future)

Orchestration:
├── Docker (containerization)
├── Kubernetes (cluster management)
├── Ray (distributed task scheduling)
└── Dask (workflow orchestration)

Monitoring:
├── NVIDIA GPU Monitor (nvidia-smi)
├── Prometheus (metrics collection)
├── Grafana (visualization)
└── TensorBoard (training visualization)
```

---

## Performance Metrics to Track

When optimizing, measure and track:

### Speed Metrics
- **Total execution time** (primary objective)
- **Time per OD pair processed** (routing workload)
- **Time per damage calculation** (damage analysis)
- **Samples per second** (sensitivity analysis)

### Resource Metrics
- **GPU memory utilization** (target: 70-85%)
- **GPU compute utilization** (target: >80%)
- **Data transfer time** (GPU ↔ CPU bandwidth)
- **CPU memory peak** (during GPU-CPU sync)

### Quality Metrics
- **Speedup vs. baseline** (actual vs. theoretical)
- **Accuracy verification** (GPU results match CPU)
- **Reproducibility** (consistent results across runs)

### I/O Metrics
- **Data read time** (Parquet read performance)
- **Checkpoint write time** (recovery state)
- **Network bandwidth** (multi-node setups)

---

## Troubleshooting Common Issues

### Issue 1: GPU Out of Memory (OOM)

**Symptoms**: CUDA out of memory errors, job termination

**Solutions**:
1. **Reduce batch size**
   ```python
   batch_size = 64  # Reduce from 256
   ```

2. **Use GPU memory efficient algorithms**
   ```python
   # Avoid full matrix materialization
   for chunk in chunked_data:
       result = process_chunk(chunk)
   ```

3. **Transfer data in chunks**
   ```python
   # Don't transfer entire dataset at once
   for i in range(0, len(df), chunk_size):
       chunk = df.iloc[i:i+chunk_size]
       chunk_gpu = cudf.from_pandas(chunk)
       # Process chunk...
   ```

### Issue 2: Slow GPU Computation

**Symptoms**: GPU slower than CPU despite using GPU

**Causes & Solutions**:
1. **GPU initialization overhead dominates**
   - Solution: Increase batch size to amortize overhead

2. **Data transfer bottleneck**
   - Measure transfer time with `time.perf_counter()`
   - Solution: Keep data on GPU, avoid round-trips

3. **Memory access patterns suboptimal**
   - Solution: Use memory coalescing in custom kernels

### Issue 3: Multi-GPU Load Imbalance

**Symptoms**: Some GPUs idle while others at 100%

**Solutions**:
1. **Dynamic load balancing**
   ```python
   # Use Dask's automatic scheduling
   # Don't pin tasks to specific workers
   ```

2. **Work stealing**
   ```python
   # Ray provides automatic work stealing
   ray.init(include_dashboard=True)
   ```

---

## Validation & Testing Strategy

### Unit Testing for GPU Code
```python
import pytest
import cudf
import pandas as pd

def test_damage_calculation_gpu():
    """Verify GPU computation matches CPU"""
    # Create small test data
    cpu_data = pd.DataFrame({
        'flood_depth': [0.1, 0.5, 1.0, 1.5],
        'road_class': ['A', 'B', 'A', 'C']
    })
    
    # CPU version
    cpu_result = cpu_data.apply(calculate_damage_row, axis=1)
    
    # GPU version
    gpu_data = cudf.from_pandas(cpu_data)
    gpu_result = gpu_data.apply(calculate_damage_row).to_pandas()
    
    # Verify
    pd.testing.assert_frame_equal(
        cpu_result.reset_index(drop=True),
        gpu_result.reset_index(drop=True),
        rtol=1e-5  # Allow numerical precision differences
    )

def test_gpu_memory_cleanup():
    """Verify GPU memory is properly released"""
    import gc
    
    for _ in range(100):
        df = cudf.from_pandas(large_dataframe)
        result = df.apply(compute_something)
        del df, result
        gc.collect()
    
    # GPU memory should be freed
    assert cuda.current_context().get_memory_info()[0] < 1e8  # < 100MB
```

### Integration Testing
```python
def test_full_pipeline_gpu():
    """Test complete damage analysis pipeline on GPU"""
    # Load sample data
    sample_data = load_test_fixtures()
    
    # Run GPU pipeline
    gpu_results = run_damage_analysis_gpu(sample_data)
    
    # Run CPU pipeline (as reference)
    cpu_results = run_damage_analysis_cpu(sample_data)
    
    # Compare results
    assert np.allclose(
        gpu_results['total_damage'],
        cpu_results['total_damage'],
        rtol=0.01  # 1% tolerance for floating point
    )
```

---

## Monitoring & Profiling on GPU

### NVIDIA GPU Profiling Tools

**nvidia-smi** (Basic monitoring)
```bash
# Real-time monitoring
nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total --format=csv,noheader,nounits -l 1
```

**Nsight Systems** (Detailed profiling)
```bash
# Profile entire application
nsys profile --stats=true python scripts/3_damage_analysis.py

# View interactive timeline
nsys-ui damage_analysis.qdrep
```

**Nsight Compute** (Kernel profiling)
```bash
# Profile specific CUDA kernels
ncu --set full python -c "gpu_damage_calculation()"
```

---

## Cost-Benefit Analysis

### Estimated ROI for Different Scenarios

#### Scenario A: Single-GPU Damage Acceleration
| Metric | Value |
|--------|-------|
| Hardware Cost | $20K-30K |
| Setup Time | 2-3 weeks |
| Code Changes | 5-10% |
| Speedup | 10-30x |
| Payback Period | 2-3 months (if running daily) |

#### Scenario B: Multi-GPU Cluster
| Metric | Value |
|--------|-------|
| Hardware Cost | $200K-500K |
| Setup Time | 6-10 weeks |
| Code Changes | 20-30% |
| Speedup | 50-200x |
| Payback Period | 3-6 months (if heavy usage) |

#### Scenario C: Cloud GPU (Pay-as-you-go)
| Metric | Value |
|--------|-------|
| Hardware Cost | $0 (OPEX) |
| Setup Time | 1-2 weeks |
| Cost per run | $10-100/day |
| Speedup | 20-100x |
| Good For | Occasional large runs |

---

## Deployment Checklist

- [ ] **Week 1-2**: Profiling & baseline measurements
- [ ] **Week 2-3**: Install CUDA toolkit and RAPIDS
- [ ] **Week 3-4**: Pilot GPU acceleration on damage calculations
- [ ] **Week 4-5**: Integrate cuGraph for routing
- [ ] **Week 5-6**: Multi-GPU testing with Dask-CUDA
- [ ] **Week 6-7**: Load testing and optimization
- [ ] **Week 7-8**: Documentation and training
- [ ] **Week 8-9**: Production deployment
- [ ] **Week 9-10**: Monitoring and fine-tuning

---

## Summary & Next Steps

### Quick Wins (Implement First)
1. **Profile current bottlenecks** (1 week) → Identify top 20% of computation time
2. **CPU parallelization with Dask** (1-2 weeks) → 2-4x speedup, minimal changes
3. **GPU damage calculations** (2-3 weeks) → 10-30x speedup, high ROI

### Medium-Term (Next Phase)
1. **GPU-accelerated routing with cuGraph** (3-4 weeks) → 20-50x speedup
2. **Multi-GPU scaling with Dask-CUDA** (2-3 weeks) → 50-100x speedup
3. **Sensitivity analysis optimization** (2-3 weeks) → 20-100x speedup

### Long-Term (Strategic)
1. **Kubernetes cluster deployment** → Unlimited scaling
2. **Real-time dashboard** → Live scenario monitoring
3. **Automated parameter optimization** → ML-guided exploration

### Start Action
1. Read the [RAPIDS Getting Started](https://rapids.ai/getting-started/)
2. Install CUDA toolkit locally or use cloud GPU (AWS, Azure, GCP)
3. Run the damage calculation pilot from **Phase 3**
4. Measure actual speedups on your hardware
5. Plan next steps based on results

---

## References & Additional Resources

### Official Documentation
- RAPIDS: https://docs.rapids.ai/
- Dask: https://docs.dask.org/
- Numba: https://numba.readthedocs.io/
- cuGraph: https://docs.rapids.ai/api/cugraph/

### Tutorials & Guides
- [NVIDIA GPU Computing Best Practices](https://developer.nvidia.com/blog/)
- [Dask-CUDA Scaling](https://docs.rapids.ai/api/dask-cuda/)
- [Numba CUDA Examples](https://numba.readthedocs.io/en/stable/cuda/index.html)

### Community Resources
- [RAPIDS Community Forum](https://forums.developer.nvidia.com/c/ai-deep-learning/ai-data-analytics-rapids/)
- [Dask GitHub Discussions](https://github.com/dask/dask/discussions)
- [Stack Overflow](https://stackoverflow.com/questions/tagged/cuda+python)

---

**Last Updated**: January 2026  
**Status**: Active Development  
**Maintainers**: NISMOD Team
