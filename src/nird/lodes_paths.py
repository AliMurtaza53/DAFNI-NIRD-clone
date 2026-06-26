"""Resolve local LODES input directories and default download URLs."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_LODES8_BASE_URL = "https://lehd.ces.census.gov/data/lodes/LODES8/"

# Lowercase USPS abbreviations for the 50 states + DC (CONUS passenger build scope).
CONUS_STATE_ABBRS: tuple[str, ...] = (
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "dc", "fl",
    "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me",
    "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh",
    "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri",
    "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
)


def resolve_lodes_data_root(base_path: Path | None = None, repo_root: Path | None = None) -> Path | None:
    """Return a local LODES cache root when it exists on disk."""
    candidates: list[Path] = []
    env_root = os.getenv("NIRD_LODES_DATA_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    if base_path is not None:
        candidates.append(base_path.parent / "lodes_data")
        candidates.append(base_path / "lodes_data")
    if repo_root is not None:
        candidates.append(repo_root / "data" / "lodes_data")
    candidates.append(Path.home() / "Desktop" / "data" / "lodes_data")

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            return path
    return None


def lodes_base_url(local_root: Path | None = None) -> str:
    """Prefer a local LODES mirror; otherwise use the Census LODES8 URL."""
    if local_root is not None:
        return local_root.as_posix().rstrip("/") + "/"
    env_url = os.getenv("NIRD_LODES8_BASE_URL")
    if env_url:
        return env_url.rstrip("/") + "/"
    return DEFAULT_LODES8_BASE_URL


def od_file_path(
    state: str,
    *,
    job_type: str = "JT00",
    year: int = 2022,
    part: str = "main",
    base: str | Path | None = None,
) -> str:
    """Build the LODES OD filename or URL for one state/part."""
    st = state.lower()
    root = lodes_base_url(Path(base) if isinstance(base, Path) else None) if base is None else str(base).rstrip("/") + "/"
    return f"{root}{st}/od/{st}_od_{part}_{job_type}_{year}.csv.gz"


def crosswalk_file_path(state: str, *, base: str | Path | None = None) -> str:
    st = state.lower()
    root = lodes_base_url(Path(base) if isinstance(base, Path) else None) if base is None else str(base).rstrip("/") + "/"
    return f"{root}{st}/{st}_xwalk.csv.gz"
