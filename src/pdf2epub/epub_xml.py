"""Pure builders for the XML/XHTML documents inside an EPUB 3 package."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from xml.dom import minidom
from xml.sax.saxutils import escape

from .metadata import BookDescription

MEDIA_TYPES = {".gif": "image/gif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


@dataclass
class TocEntry:
    title: str
    href: str
    anchor: str = ""
    children: list["TocEntry"] = field(default_factory=list)

    def url(self) -> str:
        return quote(self.href) + (f"#{quote(self.anchor, safe='')}" if self.anchor else "")


def attr(value: str) -> str:
    """Escape a value for use inside a double-quoted XML attribute."""
    return escape(value, {'"': "&quot;"})


def chapter_href(index: int, markdown_filename: str) -> str:
    """File name of a chapter inside OPS/ (not URL-quoted)."""
    return f"s{index:05d}-{markdown_filename.split('.')[0]}.xhtml"


def chapter_label(markdown_filename: str) -> str:
    return markdown_filename.split(".")[0]


def container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "<rootfiles>\n"
        '<rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/>\n'
        "</rootfiles>\n</container>"
    )


def _element(doc, name: str, attributes: dict[str, str], text: Optional[str] = None):
    el = doc.createElement(name)
    for key, value in attributes.items():
        el.setAttribute(key, value)
    if text is not None:
        el.appendChild(doc.createTextNode(text))
    return el


_METADATA_IDS = {"dc:title": "title", "dc:creator": "creator", "dc:identifier": "pub-id"}


def package_opf(
    description: BookDescription,
    chapter_hrefs: list[str],
    image_files: list[str],
    css_files: list[str],
    modified: Optional[datetime] = None,
    *,
    math_hrefs: set[str] | None = None,
) -> str:
    """package.opf: metadata, manifest, spine and guide."""
    doc = minidom.Document()
    package = _element(doc, "package", {
        "xmlns": "http://www.idpf.org/2007/opf",
        "version": "3.0",
        "xml:lang": description.language,
        "unique-identifier": "pub-id",
    })

    metadata = _element(doc, "metadata", {"xmlns:dc": "http://purl.org/dc/elements/1.1/"})
    for key, value in description.metadata.items():
        if value:
            ident = _METADATA_IDS.get(key)
            metadata.appendChild(_element(doc, key, {"id": ident} if ident else {}, value))
    modified = modified or datetime.now(timezone.utc)
    metadata.appendChild(_element(
        doc, "meta", {"property": "dcterms:modified"}, modified.strftime("%Y-%m-%dT%H:%M:%SZ")))

    manifest = doc.createElement("manifest")
    manifest.appendChild(_element(doc, "item", {
        "id": "toc", "properties": "nav", "href": "TOC.xhtml", "media-type": "application/xhtml+xml"}))
    manifest.appendChild(_element(doc, "item", {
        "id": "ncx", "href": "toc.ncx", "media-type": "application/x-dtbncx+xml"}))
    manifest.appendChild(_element(doc, "item", {
        "id": "titlepage", "href": "titlepage.xhtml", "media-type": "application/xhtml+xml"}))
    for i, href in enumerate(chapter_hrefs):
        item = _element(doc, "item", {
            "id": f"s{i:05d}",
            "href": quote(href),
            "media-type": "application/xhtml+xml",
        })
        if math_hrefs and href in math_hrefs:
            item.setAttribute("properties", "mathml")
        manifest.appendChild(item)
    for i, image in enumerate(image_files):
        item = _element(doc, "item", {"id": f"image-{i:05d}", "href": f"images/{quote(image)}"})
        media_type = MEDIA_TYPES.get(Path(image).suffix.lower())
        if media_type:
            item.setAttribute("media-type", media_type)
        if image == description.cover_image:
            item.setAttribute("properties", "cover-image")
            # EPUB 2 readers look for <meta name="cover">
            metadata.appendChild(_element(doc, "meta", {"name": "cover", "content": f"image-{i:05d}"}))
        manifest.appendChild(item)
    for i, css in enumerate(css_files):
        manifest.appendChild(_element(doc, "item", {
            "id": f"css-{i:05d}", "href": f"css/{css}", "media-type": "text/css"}))

    spine = _element(doc, "spine", {"toc": "ncx"})
    spine.appendChild(_element(doc, "itemref", {"idref": "titlepage", "linear": "yes"}))
    for i in range(len(chapter_hrefs)):
        spine.appendChild(_element(doc, "itemref", {"idref": f"s{i:05d}", "linear": "yes"}))

    guide = doc.createElement("guide")
    guide.appendChild(_element(doc, "reference", {
        "type": "cover", "title": "Cover image", "href": "titlepage.xhtml"}))

    for part in (metadata, manifest, spine, guide):
        package.appendChild(part)
    doc.appendChild(package)
    return doc.toprettyxml()


def cover_xhtml(title: str, authors: Optional[str], lang: str) -> str:
    """Simple text title page."""
    lang = attr(lang)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}">
<head>
<title>Cover Page</title>
<style type="text/css">
body {{
    margin: 0;
    padding: 0;
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    font-family: serif;
}}
.cover {{
    padding: 3em;
    text-align: center;
    border: 1px solid #ccc;
    max-width: 80%;
}}
h1 {{
    font-size: 2em;
    margin-bottom: 1em;
    line-height: 1.2;
    color: #333;
}}
p {{
    font-size: 1.2em;
    font-style: italic;
    color: #666;
    line-height: 1.4;
}}
</style>
</head>
<body>
    <div class="cover">
        <h1>{escape(title)}</h1>
        <p>{escape(authors) if authors else ''}</p>
    </div>
</body>
</html>"""


def _nav_items(entries: list[TocEntry]) -> str:
    return "".join(
        f'<li><a href="{entry.url()}">{escape(entry.title)}</a>'
        + (f"<ol>{_nav_items(entry.children)}</ol>" if entry.children else "")
        + "</li>"
        for entry in entries
    )


def nav_xhtml(css_files: list[str], toc: list[TocEntry], lang: str) -> str:
    """EPUB 3 navigation document (TOC.xhtml)."""
    lang = attr(lang)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">\n',
        '<head>\n<meta http-equiv="default-style" content="text/html; charset=utf-8"/>\n',
        "<title>Contents</title>\n",
    ]
    parts += [f'<link rel="stylesheet" href="css/{css}" type="text/css"/>\n' for css in css_files]
    parts.append('</head>\n<body>\n<nav epub:type="toc" role="doc-toc" id="toc">\n<h2>Contents</h2>\n<ol epub:type="list">')
    parts.append(_nav_items(toc))
    parts.append("</ol>\n</nav>\n</body>\n</html>")
    return "".join(parts)


def _toc_depth(entries: list[TocEntry]) -> int:
    return max((1 + _toc_depth(entry.children) for entry in entries), default=0)


def _nav_points(entries: list[TocEntry], indices: count) -> str:
    parts = []
    for entry in entries:
        i = next(indices)
        parts += [
            f'<navPoint id="navpoint-{i}" playOrder="{i + 1}">\n',
            f"<navLabel>\n<text>{escape(entry.title)}</text>\n</navLabel>",
            f'<content src="{entry.url()}"/>',
            _nav_points(entry.children, indices),
            " </navPoint>",
        ]
    return "".join(parts)


def ncx(toc: list[TocEntry], uid: str, title: str, lang: str) -> str:
    """EPUB 2 table of contents (toc.ncx) for older readers."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" xml:lang="{attr(lang)}" version="2005-1">\n',
        "<head>\n",
        f'<meta name="dtb:uid" content="{attr(uid)}"/>\n',
        f'<meta name="dtb:depth" content="{max(1, _toc_depth(toc))}"/>\n',
        '<meta name="dtb:totalPageCount" content="0"/>\n',
        '<meta name="dtb:maxPageNumber" content="0"/>\n',
        "</head>\n",
        f"<docTitle><text>{escape(title)}</text></docTitle>\n",
        "<navMap>\n",
    ]
    parts.append(_nav_points(toc, count()))
    parts.append("</navMap>\n</ncx>")
    return "".join(parts)


def chapter_xhtml(body_html: str, title: str, css_files: list[str], lang: str) -> str:
    """Wrap a chapter body in an XHTML document (<title> is required)."""
    lang = attr(lang)
    links = "".join(
        f'<link rel="stylesheet" href="css/{css}" type="text/css" media="all"/>' for css in css_files)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:m="http://www.w3.org/1998/Math/MathML" xml:lang="{lang}" lang="{lang}">
<head>
    <meta http-equiv="default-style" content="text/html; charset=utf-8"/>
    <title>{escape(title)}</title>
    {links}
</head>
<body>
{body_html}
</body>
</html>"""
