"""Profile runner for scripts 1-4 plus postprocess

Creates:
- profiles/{script_name}.prof  (cProfile binary)
- profiles/{script_name}_summary.txt (top 20 by cumulative time)
- profiles/timings.csv (script, wall_time_seconds)
- profiles/timings.png (bar chart of wall times)

Run: python tools/profile_runner.py

Note: This script does not commit results; it writes to local `profiles/`.
"""
import os
import subprocess
import time
import csv
import pstats
import sys
from contextlib import redirect_stdout
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PROFILES_DIR = os.path.join(ROOT, 'profiles')
SCRIPTS = [
    ('scripts/1_network_flow_model_revision.py', ['1', '1']),
    'scripts/2_intersection_analysis.py',
    'scripts/3_damage_analysis.py',
    'scripts/3_postprocess_damage.py',
    ('scripts/4_rerouting_and_recovery_scenario_loop.py', ['0', '0', '1', '1']),
]

os.makedirs(PROFILES_DIR, exist_ok=True)

timings = []

for entry in SCRIPTS:
    if isinstance(entry, tuple):
        script_rel, script_args = entry
    else:
        script_rel, script_args = entry, []
    script_path = os.path.join(ROOT, script_rel)
    name = os.path.splitext(os.path.basename(script_path))[0]
    prof_file = os.path.join(PROFILES_DIR, f'{name}.prof')
    summary_file = os.path.join(PROFILES_DIR, f'{name}_summary.txt')
    time_file = os.path.join(PROFILES_DIR, f'{name}_time.txt')

    if not os.path.exists(script_path):
        with open(summary_file, 'w') as fh:
            fh.write(f'SCRIPT NOT FOUND: {script_path}\n')
        print(f'SKIP MISSING: {script_rel}')
        timings.append((name, None))
        continue

    print(f'Profiling {script_rel} -> {prof_file}')
    start = time.time()
    try:
        # Run under cProfile via subprocess to isolate environment
        subprocess.run([
            sys.executable, '-m', 'cProfile', '-o', prof_file, script_path, *script_args
        ], check=True)
        elapsed = time.time() - start
        timings.append((name, elapsed))
        # Write a brief timing file
        with open(time_file, 'w') as tf:
            tf.write(f'{elapsed:.3f}\n')
        # Load pstats and write top entries
        ps = pstats.Stats(prof_file)
        with open(summary_file, 'w') as sf:
            sf.write(f'Profile summary for {script_rel}\n')
            sf.write(f'Wall time (s): {elapsed:.3f}\n\n')
            with redirect_stdout(sf):
                ps.strip_dirs().sort_stats('cumulative').print_stats(20)
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        timings.append((name, None))
        with open(summary_file, 'w') as sf:
            sf.write(f'ERROR running {script_rel}: {e}\n')
        print(f'ERROR profiling {script_rel}: {e}')

# Write timings.csv
csv_file = os.path.join(PROFILES_DIR, 'timings.csv')
with open(csv_file, 'w', newline='') as cf:
    writer = csv.writer(cf)
    writer.writerow(['script', 'wall_time_seconds'])
    for name, t in timings:
        writer.writerow([name, '' if t is None else f'{t:.3f}'])

# Create a bar chart for scripts that ran
names = [n for n, t in timings if t is not None]
values = [t for n, t in timings if t is not None]
if names:
    plt.figure(figsize=(8, 4))
    plt.bar(names, values, color='tab:blue')
    plt.ylabel('Wall time (s)')
    plt.title('Pipeline script wall times')
    plt.tight_layout()
    plt.savefig(os.path.join(PROFILES_DIR, 'timings.png'))
    print('WROTE:', os.path.join(PROFILES_DIR, 'timings.png'))

print('Profile run complete. Summaries in', PROFILES_DIR)
