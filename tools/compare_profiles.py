"""Helper: read cProfile .prof files and export summary CSVs for quick analysis.

Usage:
    python tools/compare_profiles.py --profiles_dir profiles --out_dir profiles/summary

Outputs:
- profiles/summary/{profile_name}_top.csv  (top 50 functions by cumulative time)
- profiles/summary/aggregate_timings.csv   (per-profile total wall time from timings.csv or computed)

This script is lightweight and intended to be used by the notebook.
"""
import os
import argparse
import pstats
import pandas as pd


def summarize_profile(prof_path, top_n=50):
    ps = pstats.Stats(prof_path)
    # get stats as list of (ncalls, tottime, cumtime, ...) keyed by func
    func_stats = []
    for func, stat in ps.stats.items():
        cc, nc, tt, ct, callers = stat
        # cc: primitive calls, nc: total calls, tt: total time, ct: cumulative time
        func_name = pstats.func_std_string(func)
        func_stats.append((func_name, nc, tt, ct))
    df = pd.DataFrame(func_stats, columns=["func", "calls", "tottime", "cumtime"]) 
    df = df.sort_values("cumtime", ascending=False).head(top_n).reset_index(drop=True)
    return df


def main(profiles_dir, out_dir, top_n=50):
    os.makedirs(out_dir, exist_ok=True)
    entries = [f for f in os.listdir(profiles_dir) if f.endswith('.prof')]
    summary_rows = []
    for prof in entries:
        prof_path = os.path.join(profiles_dir, prof)
        name = os.path.splitext(prof)[0]
        try:
            df = summarize_profile(prof_path, top_n=top_n)
            out_csv = os.path.join(out_dir, f"{name}_top.csv")
            df.to_csv(out_csv, index=False)
            total_cum = df['cumtime'].sum()
            summary_rows.append((name, prof_path, total_cum))
            print(f"WROTE: {out_csv}")
        except Exception as e:
            print(f"Failed to parse {prof_path}: {e}")

    # write aggregate
    agg = pd.DataFrame(summary_rows, columns=["profile", "path", "top_cumtime"]) 
    agg_out = os.path.join(out_dir, 'aggregate_top_cumtime.csv')
    agg.to_csv(agg_out, index=False)
    print("WROTE:", agg_out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profiles_dir', default='profiles')
    parser.add_argument('--out_dir', default='profiles/summary')
    parser.add_argument('--top_n', type=int, default=50)
    args = parser.parse_args()
    main(args.profiles_dir, args.out_dir, top_n=args.top_n)
