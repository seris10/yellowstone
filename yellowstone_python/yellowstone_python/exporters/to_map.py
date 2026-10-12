"""M11 to_map: reproject field PNGs into the midway_macro frame (stub)."""
from __future__ import annotations


def reproject_to_macro(field_png: str, out_png: str) -> str:
    """Fields are already authored in macro extent; plain copy."""
    import shutil
    shutil.copyfile(field_png, out_png)
    return out_png
