"""
Markdown workspace -> EPUB.

assemble_epub() is pure: it turns already-loaded inputs into the list of files
of the EPUB container. build_epub() reads the workspace and writes the file.
"""
import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import epub_xml, html, sections, workspace
from .images import optimize_image
from .metadata import BookDescription

log = logging.getLogger(__name__)

MIMETYPE = b"application/epub+zip"
DEFAULT_CSS_CONTENT = b"""body { font-family: serif; line-height: 1.5; margin: 5%; }
h1, h2, h3, h4, h5, h6 { font-family: sans-serif; }
img { max-width: 100%; height: auto; }
pre, code { font-family: monospace; font-size: 0.9em; }
"""


@dataclass
class EpubInputs:
    """Everything needed to build an EPUB, already loaded into memory."""
    description: BookDescription
    chapter_markdown: dict[str, str]          # markdown filename -> text
    images: dict[str, bytes] = field(default_factory=dict)       # images/ filename -> bytes
    stylesheets: dict[str, bytes] = field(default_factory=dict)  # css/ filename -> bytes
    toc_hints: dict[str, set[tuple[str, int]]] = field(default_factory=dict)


def _optimized_or_raw(name: str, data: bytes) -> bytes:
    try:
        return optimize_image(data, name)
    except Exception as e:
        log.warning("Failed to optimise image %s, storing it unchanged: %s", name, e)
        return data


def _chapter_toc(parts: list[sections.Section], hrefs: list[str]) -> list[epub_xml.TocEntry]:
    roots = []
    parents = []

    def add(level, entry):
        while parents and parents[-1][0] >= level:
            parents.pop()
        siblings = parents[-1][1].children if parents else roots
        siblings.append(entry)
        parents.append((level, entry))

    for part, href in zip(parts, hrefs, strict=True):
        add(part.level, epub_xml.TocEntry(part.title, href))
        for heading in part.subheadings:
            add(heading.level, epub_xml.TocEntry(heading.title, href, heading.anchor))
        # In-file subheadings cannot be parents of a later section.
        while parents[-1][0] > part.level:
            parents.pop()
    return roots


def _chapter_pages(
    body: str, markdown: str, start: int, split_level: str, used_slugs: set[str],
    hints: set[tuple[str, int]] | None,
) -> tuple[list[tuple[str, str, str]], list[epub_xml.TocEntry]]:
    if split_level == "none":
        href = epub_xml.chapter_href(start, markdown)
        return [(href, Path(markdown).stem, body)], [epub_xml.TocEntry(epub_xml.chapter_label(markdown), href)]

    parts = sections.split_sections(body, Path(markdown).stem, split_level, hints)
    hrefs = []
    for index, part in enumerate(parts, start):
        name = sections.unique_name(sections.slug(part.title), used_slugs)
        used_slugs.add(name)
        hrefs.append(epub_xml.chapter_href(index, name))
    bodies = sections.render_sections(parts, hrefs)
    return [(href, part.title, body) for href, part, body in zip(hrefs, parts, bodies, strict=True)], _chapter_toc(parts, hrefs)


def assemble_epub(
    inputs: EpubInputs, modified: Optional[datetime] = None, *, split_level: str = "auto",
) -> list[tuple[str, bytes]]:
    """
    Build the (path, content) entries of the EPUB, in archive order.

    Images referenced by a chapter are optimised; unreferenced images are
    included unchanged. The mimetype entry comes first, as the spec requires.
    """
    if split_level not in sections.SPLIT_LEVELS:
        raise ValueError(f"Invalid split level: {split_level!r}")
    description = inputs.description
    lang = description.language
    css_files = description.css_files()
    image_names = sorted(inputs.images)

    chapter_entries = []
    chapter_hrefs = []
    math_hrefs = set()
    referenced: dict[str, None] = {}
    toc = []
    used_slugs = set()
    for chapter in description.unique_chapters():
        body, refs = html.chapter_body(inputs.chapter_markdown[chapter.markdown], image_names)
        for name in refs.missing:
            log.warning("Image not found: %s", name)
        referenced.update(dict.fromkeys(refs.referenced))
        pages, chapter_toc = _chapter_pages(
            body, chapter.markdown, len(chapter_hrefs), split_level, used_slugs,
            inputs.toc_hints.get(chapter.markdown),
        )
        toc.extend(chapter_toc)
        chapter_css = description.default_css + ([chapter.css] if chapter.css else [])
        for href, title, content in pages:
            chapter_hrefs.append(href)
            if split_level != "none" and re.search(r"<(?:[\w.-]+:)?math(?:\s|>)", content):
                math_hrefs.add(href)
            xhtml = epub_xml.chapter_xhtml(content, title, chapter_css, lang)
            chapter_entries.append((f"OPS/{href}", xhtml.encode()))

    entries: list[tuple[str, bytes]] = [
        ("mimetype", MIMETYPE),
        ("META-INF/container.xml", epub_xml.container_xml().encode()),
        ("OPS/package.opf", epub_xml.package_opf(
            description, chapter_hrefs, image_names, css_files, modified, math_hrefs=math_hrefs).encode()),
        ("OPS/titlepage.xhtml", epub_xml.cover_xhtml(
            description.title, description.authors, lang).encode()),
    ]

    entries += chapter_entries
    entries += [(f"OPS/images/{name}", _optimized_or_raw(name, inputs.images[name])) for name in referenced]
    entries += [
        ("OPS/TOC.xhtml", epub_xml.nav_xhtml(description.default_css, toc, lang).encode()),
        ("OPS/toc.ncx", epub_xml.ncx(toc, description.identifier, description.title, lang).encode()),
    ]
    entries += [(f"OPS/images/{name}", inputs.images[name]) for name in image_names if name not in referenced]
    entries += [(f"OPS/css/{css}", inputs.stylesheets.get(css, DEFAULT_CSS_CONTENT)) for css in css_files]
    return entries


def write_epub(entries: list[tuple[str, bytes]], output_path: Path) -> None:
    """Write entries to a ZIP; mimetype stored uncompressed, the rest deflated."""
    with zipfile.ZipFile(output_path, "w") as archive:
        for name, data in entries:
            compression = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            archive.writestr(name, data, compression)


def load_inputs(
    work_dir: Path,
    description: BookDescription,
    chapter_markdown: Optional[dict[str, str]] = None,
) -> EpubInputs:
    """Read chapters, images and stylesheets from the workspace."""
    chapter_markdown = dict(chapter_markdown or {})
    for chapter in description.unique_chapters():
        if chapter.markdown not in chapter_markdown:
            chapter_markdown[chapter.markdown] = (work_dir / chapter.markdown).read_text(encoding="utf-8")
    image_dir = work_dir / workspace.IMAGES_DIR
    images = {name: (image_dir / name).read_bytes() for name in workspace.image_files(work_dir)}
    css_dir = work_dir / workspace.CSS_DIR
    stylesheets = {}
    for css in description.css_files():
        data = workspace.read_bytes_if_exists(css_dir / css)
        if data is not None:
            stylesheets[css] = data
    return EpubInputs(description, chapter_markdown, images, stylesheets)


def _load_toc_hints(work_dir: Path, markdown: str) -> set[tuple[str, int]]:
    path = work_dir / f"{Path(markdown).stem}_metadata.json"
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as error:
        log.warning("Ignoring Marker TOC hints in %s: %s", path, error)
        return set()
    toc = metadata.get("table_of_contents") if isinstance(metadata, dict) else None
    return {
        (sections.normalize_label(item["title"]).casefold(), item["heading_level"])
        for item in (toc if isinstance(toc, list) else [])
        if isinstance(item, dict) and isinstance(item.get("title"), str)
        and type(item.get("heading_level")) is int and 1 <= item["heading_level"] <= 6
    }


def build_epub(
    work_dir: Path,
    output_path: Path,
    description: BookDescription,
    chapter_markdown: Optional[dict[str, str]] = None,
    *,
    split_level: str = "auto",
) -> Path:
    """Build an EPUB from a workspace. chapter_markdown overrides file contents."""
    inputs = load_inputs(work_dir, description, chapter_markdown)
    if split_level == "auto":
        inputs.toc_hints = {md: _load_toc_hints(work_dir, md) for md in inputs.chapter_markdown}
    write_epub(assemble_epub(inputs, split_level=split_level), output_path)
    log.info("EPUB created: %s", output_path)
    return output_path


def default_epub_path(work_dir: Path) -> Path:
    """Upstream behaviour: <work_dir>/<work_dir name>.epub."""
    return work_dir / f"{work_dir.name}.epub"
