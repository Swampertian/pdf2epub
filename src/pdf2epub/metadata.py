"""
Book description: Dublin Core metadata, stylesheets, chapter list and cover.

Serialised as description.json in the workspace (same format as upstream).
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import workspace

DEFAULT_CSS = "style.css"
DEFAULT_LANGUAGE = "en"
DEFAULT_TITLE = "Untitled Document"


_PLACEHOLDER_TITLE = re.compile(r"^(untitled|unknown|no title)\b|\.[a-z0-9]{2,4}$", re.IGNORECASE)
_PDF_DATE = re.compile(r"^(?:D:)?(\d{4})(\d{2})(\d{2})")


def default_metadata(now: datetime, title: str = DEFAULT_TITLE) -> dict[str, str]:
    """Dublin Core fields used when neither description.json nor the PDF has a value."""
    return {
        "dc:title": title,
        "dc:creator": "Unknown Author",
        "dc:identifier": f"id-{now.strftime('%Y%m%d%H%M%S')}",
        "dc:language": DEFAULT_LANGUAGE,
        "dc:rights": "All rights reserved",
        "dc:publisher": "PDF2EPUB",
        "dc:date": now.strftime("%Y-%m-%d"),
    }


def _pdf_date(value: str) -> Optional[str]:
    """PDF date string (D:YYYYMMDDHHmmSS...) as YYYY-MM-DD, or None."""
    match = _PDF_DATE.match(value.strip())
    return "-".join(match.groups()) if match else None


def metadata_from_pdf_info(info: dict[str, str]) -> dict[str, str]:
    """Dublin Core fields from a PDF's document information dictionary."""
    title = info.get("Title", "").strip()
    author = info.get("Author", "").strip()
    date = _pdf_date(info.get("CreationDate", ""))
    metadata = {}
    if title and not _PLACEHOLDER_TITLE.search(title):
        metadata["dc:title"] = title
    if author:
        metadata["dc:creator"] = author
    if date:
        metadata["dc:date"] = date
    return metadata


@dataclass(frozen=True)
class Chapter:
    markdown: str
    css: str = ""


@dataclass
class BookDescription:
    metadata: dict[str, str] = field(default_factory=dict)
    default_css: list[str] = field(default_factory=lambda: [DEFAULT_CSS])
    chapters: list[Chapter] = field(default_factory=list)
    cover_image: Optional[str] = None

    @property
    def title(self) -> str:
        return self.metadata.get("dc:title", "Untitled Document")

    @property
    def authors(self) -> Optional[str]:
        return self.metadata.get("dc:creator")

    @property
    def identifier(self) -> str:
        return self.metadata.get("dc:identifier", "")

    @property
    def language(self) -> str:
        return self.metadata.get("dc:language", "").strip() or DEFAULT_LANGUAGE

    def unique_chapters(self) -> list[Chapter]:
        """Chapters in order, each markdown file once."""
        seen, result = set(), []
        for chapter in self.chapters:
            if chapter.markdown not in seen:
                seen.add(chapter.markdown)
                result.append(chapter)
        return result

    def css_files(self) -> list[str]:
        """Default stylesheets followed by chapter-specific ones, without duplicates."""
        files = list(self.default_css)
        for chapter in self.chapters:
            if chapter.css and chapter.css not in files:
                files.append(chapter.css)
        return files

    def with_chapters_from(self, markdown_filenames: list[str]) -> "BookDescription":
        """Fill chapters from the workspace's markdown files when none are listed."""
        if self.chapters:
            return self
        chapters = [Chapter(name) for name in markdown_filenames]
        return BookDescription(self.metadata, self.default_css, chapters, self.cover_image)

    @classmethod
    def from_dict(cls, data: dict) -> "BookDescription":
        return cls(
            metadata=dict(data.get("metadata", {})),
            default_css=list(data.get("default_css", [DEFAULT_CSS])),
            chapters=[Chapter(c["markdown"], c.get("css", "")) for c in data.get("chapters", [])],
            cover_image=data.get("cover_image"),
        )

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "default_css": self.default_css,
            "chapters": [{"markdown": c.markdown, "css": c.css} for c in self.chapters],
            "cover_image": self.cover_image,
        }

    @classmethod
    def load(cls, work_dir: Path) -> "BookDescription":
        return cls.from_dict(workspace.load_description_json(work_dir))

    def save(self, work_dir: Path) -> None:
        workspace.save_description_json(work_dir, self.to_dict())

    @classmethod
    def for_workspace(cls, work_dir: Path, now: Optional[datetime] = None,
                      pdf_metadata: Optional[dict[str, str]] = None,
                      fallback_title: str = DEFAULT_TITLE) -> "BookDescription":
        """
        Description for a workspace, without asking anything.

        Each field comes from description.json if saved there, else from the
        PDF's own metadata, else a default (the title falls back to fallback_title).
        """
        description = cls.load(work_dir)
        description.metadata = {
            **default_metadata(now or datetime.now(), fallback_title),
            **(pdf_metadata or {}),
            **description.metadata,
        }
        return description.with_chapters_from(workspace.markdown_files(work_dir))
