"""to_map: copy a field PNG into the midway_macro frame after size check."""
from __future__ import annotations


def reproject_to_macro(field_png: str, out_png: str,
                       expected_size_px: tuple[int, int] | None = None) -> str:
    """Copy a field PNG whose grid is the macro frame"""
    import shutil

    if expected_size_px is not None:
        from PIL import Image
        with Image.open(field_png) as src:
            if tuple(src.size) != tuple(expected_size_px):
                raise ValueError(
                    f"{field_png} is {tuple(src.size)}; macro frame is "
                    f"{tuple(expected_size_px)}")
    shutil.copyfile(field_png, out_png)
    return out_png
