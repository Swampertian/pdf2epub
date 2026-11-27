"""
File I/O for the intermediate workspace: one directory per book holding the
markdown, marker metadata, images/, optional css/ and description.json.
"""
import io
import json
import logging
from pathlib import Path
from typing import Any

from PIL import Image

from .extraction import Extraction

log = logging.getLogger(__name__)

IMAGES_DIR = "images"
CSS_DIR = "css"
DESCRIPTION_FILE = "description.json"
IMAGE_EXTENSIONS = ("gif", "jpg", "jpeg", "png")


class InputError(Exception):
    """Raised for invalid user-supplied input paths."""


def default_output_dir(pdf_path: Path) -> Path:
    """Directory named after the PDF, next to it."""
    return pdf_path.parent / pdf_path.stem


def find_pdfs(input_path: Path) -> list[Path]:
    """All PDFs in a directory, or the single given PDF file."""
    if input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))
        if not pdfs:
            raise InputError(f"No PDF files found in directory: {input_path}")
        return pdfs
    if not input_path.is_file():
        raise InputError(f"Input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise InputError(f"Input file must be a PDF: {input_path}")
    return [input_path]


def _to_pil(image_data: Any) -> Image.Image:
    """Accept the image representations marker may return."""
    if isinstance(image_data, Image.Image):
        return image_data
    if isinstance(image_data, bytes):
        return Image.open(io.BytesIO(image_data))
    if isinstance(image_data, str) and Path(image_data).exists():
        return Image.open(image_data)
    raise TypeError(f"unsupported image data: {type(image_data).__name__}")


def save_images(images: dict[str, Any], image_dir: Path) -> int:
    """Save marker images under their original names. Returns the count saved."""
    if not images:
        return 0
    image_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for filename, image_data in images.items():
        if not image_data:
            continue
        try:
            _to_pil(image_data).save(image_dir / filename)
            saved += 1
        except Exception as e:
            log.warning("Could not save image %s: %s", filename, e)
    return saved


def save_extraction(extraction: Extraction, work_dir: Path, stem: str) -> Path:
    """Write markdown, metadata JSON and images. Returns the markdown path."""
    work_dir.mkdir(parents=True, exist_ok=True)
    md_path = work_dir / f"{stem}.md"
    md_path.write_text(extraction.markdown, encoding="utf-8")
    meta_path = work_dir / f"{stem}_metadata.json"
    meta_path.write_text(json.dumps(extraction.metadata, indent=2), encoding="utf-8")
    count = save_images(extraction.images, work_dir / IMAGES_DIR)
    log.info("Saved %s, %s and %d images", md_path.name, meta_path.name, count)
    return md_path


def close_images(images: dict[str, Any]) -> None:
    """Release PIL images returned by marker."""
    for img in images.values():
        if isinstance(img, Image.Image):
            img.close()
    images.clear()


def markdown_files(work_dir: Path) -> list[str]:
    """Sorted markdown filenames in the workspace."""
    return sorted(p.name for p in work_dir.glob("*.md"))


def image_files(work_dir: Path) -> list[str]:
    """Sorted image filenames in images/ with a supported extension."""
    image_dir = work_dir / IMAGES_DIR
    if not image_dir.is_dir():
        return []
    return sorted(
        p.name for p in image_dir.iterdir()
        if p.is_file() and p.name.split(".")[-1] in IMAGE_EXTENSIONS
    )


def read_bytes_if_exists(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def load_description_json(work_dir: Path) -> dict:
    path = work_dir / DESCRIPTION_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_description_json(work_dir: Path, data: dict) -> None:
    (work_dir / DESCRIPTION_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
