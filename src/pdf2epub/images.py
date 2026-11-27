"""In-memory image optimisation for EPUB packaging."""
import io
from pathlib import Path

from PIL import Image

MAX_DIMENSION = 1800
JPEG_QUALITY = 85


def optimize_image(data: bytes, filename: str, max_dimension: int = MAX_DIMENSION) -> bytes:
    """
    Downscale to max_dimension and recompress JPEG/PNG images.

    Other formats are returned unchanged (upstream converted them to JPEG but
    kept the original name, which then failed and fell back to the raw bytes).
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png"):
        return data
    with Image.open(io.BytesIO(data)) as img:
        if img.mode == "RGBA":
            img = img.convert("RGB")
        ratio = min(max_dimension / max(img.size), 1.0)
        if ratio < 1.0:
            img = img.resize(tuple(int(d * ratio) for d in img.size), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        if suffix == ".png":
            img.save(out, "PNG", optimize=True)
        else:
            img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()
