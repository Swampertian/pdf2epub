"""
Book description: Dublin Core metadata, stylesheets, chapter list and cover.

Serialised as description.json in the workspace (same format as upstream).
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import workspace

DEFAULT_CSS = "style.css"
DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class MetadataField:
    key: str
    label: str
    default: str


def metadata_fields(existing: dict[str, str], now: datetime) -> list[MetadataField]:
    """Editable Dublin Core fields with defaults taken from existing values."""
    def field_(key, label, fallback):
        return MetadataField(key, label, existing.get(key, fallback))

    return [
        field_("dc:title", "Title", "Untitled Document"),
        field_("dc:creator", "Author(s)", "Unknown Author"),
        field_("dc:identifier", "Unique Identifier", f"id-{now.strftime('%Y%m%d%H%M%S')}"),
        field_("dc:language", "Language (e.g., en, de, fr)", DEFAULT_LANGUAGE),
        field_("dc:rights", "Rights", "All rights reserved"),
        field_("dc:publisher", "Publisher", "PDF2EPUB"),
        field_("dc:date", "Publication Date (YYYY-MM-DD)", now.strftime("%Y-%m-%d")),
    ]


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
    def for_workspace(cls, work_dir: Path, now: Optional[datetime] = None) -> "BookDescription":
        """Non-interactive description: saved values, defaults for the rest."""
        description = cls.load(work_dir)
        fields = metadata_fields(description.metadata, now or datetime.now())
        description.metadata = {f.key: f.default for f in fields}
        return description.with_chapters_from(workspace.markdown_files(work_dir))
