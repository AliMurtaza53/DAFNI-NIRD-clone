import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SUMDIR = BASE / 'profiles' / 'summary'
OUTDIR = BASE / 'profiles' / 'figures'
OUTDIR.mkdir(parents=True, exist_ok=True)

# Files
baseline = SUMDIR / '2_intersection_analysis_depth30_event1_candidate_baseline_current_top.csv'
candidate = SUMDIR / '2_intersection_analysis_depth30_event1_candidate_C_cache_top.csv'

# Read
b = pd.read_csv(baseline)
c = pd.read_csv(candidate)

# Normalize function labels
b['func'] = b['func'].astype(str)
c['func'] = c['func'].astype(str)

# Choose top by baseline cumtime
topn = 20
b_top = b.sort_values('cumtime', ascending=False).head(topn).copy()
# ensure candidate values exist for same funcs
merged = b_top[['func','cumtime']].merge(c[['func','cumtime']], on='func', how='left', suffixes=('_baseline','_candidate'))
merged = merged.fillna(0)

# Plot top-20 baseline cumtime
plt.figure(figsize=(10,8))
plt.barh(merged['func'][::-1], merged['cumtime_baseline'][::-1], color='tab:blue')
plt.xlabel('Cumulative time (s)')
plt.title('Top 20 functions by cumulative time (Script 2) - Baseline')
plt.tight_layout()
plt.savefig(OUTDIR / '2_intersection_top20_baseline.png', dpi=150)
plt.close()

# Side-by-side comparison for these top funcs
x = range(len(merged))
width = 0.4
plt.figure(figsize=(12,10))
plt.barh([i - width/2 for i in x][::-1], merged['cumtime_baseline'][::-1], height=width, label='baseline')
plt.barh([i + width/2 for i in x][::-1], merged['cumtime_candidate'][::-1], height=width, label='candidate_C')
plt.yticks(list(x[::-1]), merged['func'][::-1])
plt.xlabel('Cumulative time (s)')
plt.title('Baseline vs Candidate C cumulative time (Top 20 functions)')
plt.legend()
plt.tight_layout()
plt.savefig(OUTDIR / '2_intersection_compare_top20_baseline_vs_candidateC.png', dpi=150)
plt.close()

# Also produce top-50 aggregate comparison (stacked or side-by-side)
topn2 = 50
b_top50 = b.sort_values('cumtime', ascending=False).head(topn2)
# merge by func
merged50 = b_top50[['func','cumtime']].merge(c[['func','cumtime']], on='func', how='left', suffixes=('_baseline','_candidate')).fillna(0)
# save CSV
merged50.to_csv(OUTDIR / '2_intersection_compare_top50_baseline_vs_candidateC.csv', index=False)

# Simple bar of baseline vs candidate total cumtime per function for top50 (baseline order)
plt.figure(figsize=(10,20))
ind = list(range(len(merged50)))
plt.barh(ind[::-1], merged50['cumtime_baseline'][::-1], color='tab:blue', alpha=0.8, label='baseline')
plt.barh(ind[::-1], merged50['cumtime_candidate'][::-1], color='tab:orange', alpha=0.6, label='candidate_C')
plt.yticks(ind[::-1], merged50['func'][::-1])
plt.xlabel('Cumulative time (s)')
plt.title('Top 50 functions comparison: baseline vs candidate C')
plt.legend()
plt.tight_layout()
plt.savefig(OUTDIR / '2_intersection_compare_top50_baseline_vs_candidateC.png', dpi=150)
plt.close()

print('WROTE FIGURES TO', OUTDIR)
