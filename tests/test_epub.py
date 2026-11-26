import io
import zipfile
from datetime import datetime, timezone
from xml.dom import minidom

from PIL import Image

from pdf2epub import epub
from pdf2epub.metadata import BookDescription, Chapter


def png(size):
    out = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(out, "PNG")
    return out.getvalue()


def sample_inputs():
    description = BookDescription(
        metadata={"dc:title": 'A & "B"', "dc:creator": "Author", "dc:identifier": "id-1",
                  "dc:language": "pt-BR"},
        chapters=[Chapter("one.md"), Chapter("two.md", "extra.css"), Chapter("one.md")],
    )
    return epub.EpubInputs(
        description,
        {"one.md": "# One\n\n![f](big.png) $x$", "two.md": "# Two"},
        images={"big.png": png((3000, 100)), "unused.png": png((10, 10))},
        stylesheets={"extra.css": b"p{}"},
    )


def build(tmp_path):
    entries = epub.assemble_epub(sample_inputs(), datetime(2026, 1, 1, tzinfo=timezone.utc))
    path = tmp_path / "book.epub"
    epub.write_epub(entries, path)
    return zipfile.ZipFile(path)


def test_container_layout(tmp_path):
    z = build(tmp_path)
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert z.read("mimetype") == b"application/epub+zip"
    names = set(z.namelist())
    assert {"OPS/s00000-one.xhtml", "OPS/s00001-two.xhtml", "OPS/images/big.png",
            "OPS/images/unused.png", "OPS/css/style.css", "OPS/css/extra.css"} <= names
    assert "OPS/s00002-one.xhtml" not in names  # duplicate chapter listed once


def test_all_xml_well_formed_and_language(tmp_path):
    z = build(tmp_path)
    for name in z.namelist():
        if name.endswith((".xml", ".opf", ".ncx", ".xhtml")):
            doc = minidom.parseString(z.read(name))
            root = doc.documentElement
            if root.tagName in ("html", "package", "ncx"):
                assert root.getAttribute("xml:lang") == "pt-BR", name


def test_referenced_images_optimized_unreferenced_raw(tmp_path):
    z = build(tmp_path)
    assert Image.open(io.BytesIO(z.read("OPS/images/big.png"))).size == (1800, 60)
    assert z.read("OPS/images/unused.png") == sample_inputs().images["unused.png"]


def test_missing_stylesheet_gets_default(tmp_path):
    z = build(tmp_path)
    assert z.read("OPS/css/style.css") == epub.DEFAULT_CSS_CONTENT
    assert z.read("OPS/css/extra.css") == b"p{}"
