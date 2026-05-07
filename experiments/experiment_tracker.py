#!/usr/bin/env python3
"""Experiment tracker: save profiles with metadata and manage experiment structure."""
from pathlib import Path
import argparse
import json
import shutil
from datetime import datetime
import subprocess


def get_current_branch():
    """Get current git branch."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Warning: could not get branch: {e}")
        return "unknown"


def get_commit_hash():
    """Get current commit hash."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Warning: could not get commit: {e}")
        return "unknown"


def save_profile(profile_path, exp_dir, exp_id, branch, description):
    """Save profile with metadata to experiments/ directory."""
    profile_path = Path(profile_path)
    exp_dir = Path(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)

    # Copy .prof file
    prof_dest = exp_dir / profile_path.name
    shutil.copy2(profile_path, prof_dest)
    print(f"Copied .prof: {prof_dest}")

    # Save metadata
    metadata = {
        'exp_id': exp_id,
        'branch': branch or get_current_branch(),
        'commit': get_commit_hash(),
        'timestamp': datetime.utcnow().isoformat(),
        'description': description,
        'prof_file': profile_path.name,
    }
    metadata_path = exp_dir / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata: {metadata_path}")

    # Also copy .log if it exists (same name + .log)
    log_path = profile_path.with_suffix('.log')
    if log_path.exists():
        log_dest = exp_dir / log_path.name
        shutil.copy2(log_path, log_dest)
        print(f"Copied log: {log_dest}")


def main():
    parser = argparse.ArgumentParser(description='Manage experiment profiles and metadata.')
    parser.add_argument('--action', choices=['save_profile'], required=True)
    parser.add_argument('--profile_path', help='Path to .prof file')
    parser.add_argument('--exp_dir', help='Destination experiments/ subdirectory')
    parser.add_argument('--exp_id', help='Experiment ID (for metadata)')
    parser.add_argument('--branch', help='Git branch (auto-detected if not provided)')
    parser.add_argument('--description', help='Description of the experiment')

    args = parser.parse_args()

    if args.action == 'save_profile':
        save_profile(
            args.profile_path,
            args.exp_dir,
            args.exp_id,
            args.branch,
            args.description
        )


if __name__ == '__main__':
    main()
