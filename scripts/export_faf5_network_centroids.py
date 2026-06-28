"""Export FAF5 loading centroids from FAF5Network.gdb to parquet for OD mapping.

Run this once after installing the full FHWA FAF5 network geodatabase. The copy
under faf5_data/network_data must be the complete GDB (typically hundreds of MB
or larger, not a stub folder).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nird.faf5_paths import resolve_faf5_data_root
from nird.geo_runtime import configure_geo_runtime
from nird.utils import load_config
from preprocess.map_bts_od_to_network_centroids import read_network_centroid_table, write_table

LOGGER = logging.getLogger(__name__)
MIN_GDB_BYTES = 50_000_000  # full CONUS GDB is much larger than this


def gdb_payload_bytes(gdb_path: Path) -> int:
    if not gdb_path.is_dir():
        return 0
    return sum(f.stat().st_size for f in gdb_path.rglob("*") if f.is_file())


def export_centroids(
    gdb_path: Path,
    output_path: Path,
    *,
    layer: str = "FAF5_Nodes",
    summary_path: Path | None = None,
) -> Path:
    payload = gdb_payload_bytes(gdb_path)
    if payload < MIN_GDB_BYTES:
        raise FileNotFoundError(
            f"{gdb_path} looks incomplete ({payload / 1_048_576:.2f} MB). "
            "Install the full FAF5Network.gdb from FHWA/BTS (Geodatabase format), "
            "then rerun this exporter."
        )

    centroids = read_network_centroid_table(gdb_path, layer=layer)
    if "Centroid" in centroids.columns:
        loading = centroids[centroids["Centroid"] == 1].copy()
    else:
        loading = centroids.copy()

    out = write_table(loading, output_path)
    summary = {
        "gdb_path": str(gdb_path),
        "gdb_payload_mb": round(payload / 1_048_576, 2),
        "layer": layer,
        "rows_all_nodes": int(len(centroids)),
        "rows_loading_centroids": int(len(loading)),
        "output_path": str(out),
        "columns": list(loading.columns),
    }
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    LOGGER.info("Wrote %s loading centroids to %s", f"{len(loading):,}", out)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb", default=None, help="Path to FAF5Network.gdb")
    parser.add_argument(
        "--output",
        default=None,
        help="Output parquet/gpq path (default: faf5_data/processed/faf5_network_loading_centroids.gpq)",
    )
    parser.add_argument("--layer", default="FAF5_Nodes")
    args = parser.parse_args()

    configure_geo_runtime()
    config = load_config()
    base_path = Path(config["paths"]["soge_clusters"])
    faf5_root = resolve_faf5_data_root(base_path, REPO_ROOT)
    gdb = Path(args.gdb) if args.gdb else (faf5_root / "network_data" / "FAF5Network.gdb")
    out = (
        Path(args.output)
        if args.output
        else (faf5_root / "processed" / "faf5_network_loading_centroids.gpq")
    )
    summary = out.with_suffix(".summary.json")
    export_centroids(gdb, out, layer=args.layer, summary_path=summary)
    print(f"output: {out}")
    print(f"summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
