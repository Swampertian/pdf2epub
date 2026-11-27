"""PDF -> Markdown extraction with marker-pdf. No file output happens here."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Extraction:
    """What marker produces for one PDF."""
    markdown: str
    images: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def describe_device() -> str:
    """Human-readable description of the torch device marker will use."""
    import torch

    if torch.cuda.is_available():
        return f"CUDA ({torch.cuda.get_device_name(0)})"
    if torch.backends.mps.is_available():
        return "MPS (Apple Silicon)"
    return "CPU"


def load_models() -> dict:
    """
    Load marker-pdf's models.

    Loading takes several GB of (GPU) memory and noticeable time, so load once
    and pass the result to every extract_pdf() call of a batch.
    """
    from marker.models import create_model_dict

    return create_model_dict()


def page_range(start_page: Optional[int], max_pages: Optional[int]) -> Optional[list[int]]:
    """
    Build marker's page_range (explicit 0-based page indices).

    Returns None for "all pages". marker-pdf 1.x has no open-ended range, so a
    start page without max_pages also means all pages; callers may warn.
    """
    if max_pages is None:
        return None
    start = start_page or 0
    return list(range(start, start + max_pages))


def read_pdf_info(pdf_path: Path) -> dict[str, str]:
    """The PDF's document information dictionary (Title, Author, CreationDate...)."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(str(pdf_path))
    try:
        return pdf.get_metadata_dict(skip_empty=True)
    finally:
        pdf.close()


def extract_pdf(pdf_path: Path, models: dict, pages: Optional[list[int]] = None) -> Extraction:
    """Run marker on one PDF and return markdown, images and metadata."""
    from marker.converters.pdf import PdfConverter

    config = {"page_range": pages} if pages is not None else {}
    converter = PdfConverter(config=config, artifact_dict=models)
    rendered = converter(str(pdf_path))
    return Extraction(
        markdown=rendered.markdown,
        images=dict(rendered.images or {}),
        metadata=rendered.metadata,
    )
