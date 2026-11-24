"""Filesystem path helpers for user- or DB-supplied file names."""

from __future__ import annotations

import re
from pathlib import Path

# A bare file name: no separators, no leading dot, so never "..", "." or a
# hidden file. Everything NetFleet writes (stamps, .backup/.rsc/.tar.gz)
# fits this.
_SAFE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,254}")


def safe_child(base: Path, filename: str) -> Path:
    """Return base/filename, refusing anything that is not a plain file name
    directly inside base.

    A prefix check like ``str(p).startswith(str(base))`` is not enough:
    "/backups/system-old/x" starts with "/backups/system". Validate the name
    first, then compare real paths component-wise.
    """
    if not _SAFE_NAME.fullmatch(filename):
        raise ValueError("invalid file name")
    root = base.resolve()
    p = (root / filename).resolve()
    if p.parent != root:
        raise ValueError("path escapes base directory")
    return p
