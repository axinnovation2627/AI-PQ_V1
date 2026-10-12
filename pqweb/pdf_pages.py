"""PDF → 쪽 PNG."""
from __future__ import annotations

from pathlib import Path

import pymupdf


def render_pages(pdf: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            p = out_dir / f"p{i:02d}.png"
            page.get_pixmap(dpi=dpi).save(p)
            paths.append(p)
    return paths
