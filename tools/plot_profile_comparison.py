#!/usr/bin/env python3
"""Clean, focused profile comparison plot.

Loads two summary CSV files (baseline vs candidate) and produces a clean plot:
- Short function names (no file paths)
- Top-N functions by cumtime only
- Side-by-side bars for easy comparison
- Highlights delta (improvement or regression)
"""
from pathlib import Path
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json


def shorten_func_name(full_name: str, max_len=40) -> str:
    """Shorten function name: strip paths, keep module + function."""
    # Example: '/path/to/src/nird/road_functions.py:compute_maximum_speed_on_flooded_roads'
    # Output: 'road_functions:compute_maximum_speed_on_flooded_roads'
    if ':' in full_name:
        path, func = full_name.rsplit(':', 1)
        # Keep only the filename (last part of path)
        filename = Path(path).stem
        short = f"{filename}:{func}"
    else:
        short = full_name
    
    # Truncate if too long
    if len(short) > max_len:
        short = short[:max_len-3] + '...'
    return short


def load_summary_csv(csv_path):
    """Load a summary CSV from compare_profiles output."""
    df = pd.read_csv(csv_path)
    if 'func' not in df.columns or 'cumtime' not in df.columns:
        raise ValueError(f"CSV must have 'func' and 'cumtime' columns: {csv_path}")
    return df


def compare_and_plot(baseline_csv, candidate_csv, out_dir: Path, label_baseline='Baseline', label_candidate='Candidate', top_n=20):
    """Compare two profiles and plot top-N functions side-by-side."""
    baseline_df = load_summary_csv(baseline_csv)
    candidate_df = load_summary_csv(candidate_csv)
    
    # Use top-N from baseline union candidate
    union_funcs = list(dict.fromkeys(
        list(baseline_df.head(top_n)['func']) + 
        list(candidate_df.head(top_n)['func'])
    ))[:top_n]
    
    # Align data
    baseline_sub = baseline_df.set_index('func').reindex(union_funcs).fillna(0)
    candidate_sub = candidate_df.set_index('func').reindex(union_funcs).fillna(0)
    
    # Compute delta
    delta = candidate_sub['cumtime'] - baseline_sub['cumtime']
    pct_change = (delta / baseline_sub['cumtime'].replace(0, 1)) * 100
    
    # Create DataFrame for plotting
    df_plot = pd.DataFrame({
        'func_short': [shorten_func_name(f) for f in union_funcs],
        label_baseline: baseline_sub['cumtime'].values,
        label_candidate: candidate_sub['cumtime'].values,
        'delta': delta.values,
        'pct_change': pct_change.values,
    })
    
    # Sort by max cumtime (descending = top functions first)
    df_plot['max_cumtime'] = df_plot[[label_baseline, label_candidate]].max(axis=1)
    df_plot = df_plot.sort_values('max_cumtime', ascending=True)
    
    # Plot
    fig, ax = plt.subplots(figsize=(13, max(8, 0.3 * len(df_plot))))
    y_pos = range(len(df_plot))
    
    # Bars for baseline and candidate
    bars1 = ax.barh(y_pos, df_plot[label_baseline], height=0.35, label=label_baseline, alpha=0.8)
    bars2 = ax.barh([i + 0.38 for i in y_pos], df_plot[label_candidate], height=0.35, label=label_candidate, alpha=0.8)
    
    # Color code bars: green for improvement, red for regression
    for i, (bar, delta_val) in enumerate(zip(bars2, df_plot['delta'])):
        if delta_val < 0:
            bar.set_color('green')
        elif delta_val > 0:
            bar.set_color('red')
    
    ax.set_yticks([i + 0.19 for i in y_pos])
    ax.set_yticklabels(df_plot['func_short'], fontsize=9)
    ax.set_xlabel('Cumulative Time (seconds)', fontsize=11)
    ax.set_title(f'Profile Comparison: Top {top_n} Functions\n(Green = Faster, Red = Slower)', fontsize=13, fontweight='bold')
    ax.legend(loc='lower right', fontsize=10)
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    
    # Save plot
    plot_name = f"{Path(baseline_csv).stem}_vs_{Path(candidate_csv).stem}.png"
    out_path = out_dir / plot_name
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=100, bbox_inches='tight')
    print(f"WROTE PLOT: {out_path}")
    
    # Save delta table as CSV
    delta_path = out_dir / plot_name.replace('.png', '_delta.csv')
    df_plot[['func_short', label_baseline, label_candidate, 'delta', 'pct_change']].to_csv(delta_path, index=False)
    print(f"WROTE DELTA: {delta_path}")
    
    return out_path, delta_path


def main():
    parser = argparse.ArgumentParser(description='Clean, focused profile comparison.')
    parser.add_argument('--baseline', required=True, help='Path to baseline summary.csv')
    parser.add_argument('--candidate', required=True, help='Path to candidate summary.csv')
    parser.add_argument('--output', default='experiments/comparisons', help='Output directory for PNG and delta CSV')
    parser.add_argument('--label_baseline', default='Baseline', help='Label for baseline')
    parser.add_argument('--label_candidate', default='Candidate', help='Label for candidate')
    parser.add_argument('--top_n', type=int, default=20, help='Number of top functions to plot')
    args = parser.parse_args()
    
    baseline_csv = Path(args.baseline)
    candidate_csv = Path(args.candidate)
    out_dir = Path(args.output)
    
    if not baseline_csv.exists():
        raise FileNotFoundError(f"Baseline CSV not found: {baseline_csv}")
    if not candidate_csv.exists():
        raise FileNotFoundError(f"Candidate CSV not found: {candidate_csv}")
    
    compare_and_plot(
        baseline_csv,
        candidate_csv,
        out_dir,
        label_baseline=args.label_baseline,
        label_candidate=args.label_candidate,
        top_n=args.top_n
    )


if __name__ == '__main__':
    main()
