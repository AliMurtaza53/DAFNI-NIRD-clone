#!/usr/bin/env python3
"""Plot single profile summary: top-N functions and module-aggregated times.

Saves two PNGs to the output directory:
- {stem}_topN.png
- {stem}_by_module.png
"""
from pathlib import Path
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def shorten_func(full_name: str, max_len=60):
    if full_name.startswith('{'):
        return full_name
    # try to split path:lineno(name) format
    try:
        path_part = full_name.split(':', 1)[0]
        func_part = full_name.split(')', 1)[0].split('(', 1)[-1]
        name = f"{Path(path_part).stem}:{func_part}"
    except Exception:
        name = full_name
    if len(name) > max_len:
        name = name[:max_len-3] + '...'
    return name


def module_from_full(full_name: str):
    if full_name.startswith('{'):
        return full_name
    path = full_name.split(':', 1)[0]
    return Path(path).stem


def plot_top_n(df, out_path: Path, top_n=20, title=None):
    df_top = df.head(top_n).copy()
    df_top['func_short'] = df_top['func'].apply(shorten_func)
    df_top = df_top[::-1]
    plt.figure(figsize=(10, max(4, 0.35 * len(df_top))))
    plt.barh(df_top['func_short'], df_top['cumtime'], color='tab:blue')
    plt.xlabel('Cumulative time (s)')
    if title:
        plt.title(title)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=120, bbox_inches='tight')
    print('WROTE:', out_path)


def plot_by_module(df, out_path: Path, top_n=15, title=None):
    df_mod = df.copy()
    df_mod['module'] = df_mod['func'].apply(module_from_full)
    agg = df_mod.groupby('module', as_index=False)['cumtime'].sum().sort_values('cumtime', ascending=False)
    agg_top = agg.head(top_n)[::-1]
    plt.figure(figsize=(8, max(4, 0.35 * len(agg_top))))
    plt.barh(agg_top['module'], agg_top['cumtime'], color='tab:green')
    plt.xlabel('Cumulative time (s)')
    if title:
        plt.title(title)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=120, bbox_inches='tight')
    print('WROTE:', out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('summary_csv', help='Path to *_top.csv summary')
    parser.add_argument('--out_dir', default='experiments/comparisons', help='Output dir for PNGs')
    parser.add_argument('--top_n', type=int, default=20)
    args = parser.parse_args()

    csv = Path(args.summary_csv)
    if not csv.exists():
        raise FileNotFoundError(csv)
    df = pd.read_csv(csv)
    stem = csv.stem
    out_dir = Path(args.out_dir)
    plot_top_n(df, out_dir / f"{stem}_top{args.top_n}.png", top_n=args.top_n, title=f'Top {args.top_n} functions: {stem}')
    plot_by_module(df, out_dir / f"{stem}_by_module_top15.png", top_n=15, title=f'By module (top 15): {stem}')

if __name__ == '__main__':
    main()
