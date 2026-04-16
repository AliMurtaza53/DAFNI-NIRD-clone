"""Compatibility package for local runs.

This package extends the import path so `import nird...` works from the repository
root without requiring `PYTHONPATH=src`.
"""

from pkgutil import extend_path
from pathlib import Path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

src_pkg = Path(__file__).resolve().parent.parent / "src" / "nird"
if src_pkg.exists():
    __path__.append(str(src_pkg))