"""Option 1 candidate: run Script 1 with direct DuckDB Parquet outputs.

Script 1 now defaults to direct DuckDB Parquet outputs and chunked path
expansion. This wrapper remains as a compatibility entry point for previous
profile commands.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    script_path = Path(__file__).with_name("1_network_flow_model_revision.py")
    sys.argv = [str(script_path), *sys.argv[1:]]
    runpy.run_path(str(script_path), run_name="__main__")
