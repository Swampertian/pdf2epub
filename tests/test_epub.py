import io
import json
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import unquote
from xml.dom import minidom
from xml.etree import ElementTree as ET

from PIL import Image

from pdf2epub import epub
from pdf2epub.cli import parse_args
from pdf2epub.metadata import BookDescription, Chapter

MODIFIED = datetime(2026, 1, 1, tzinfo=timezone.utc)


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
    entries = epub.assemble_epub(sample_inputs(), MODIFIED)
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


def test_none_matches_pre_split_entries_byte_for_byte(monkeypatch):
    # Golden bytes were hashed before introducing splitting. Stub the image
    # encoder so the test is independent of zlib/Pillow versions; the other
    # image test covers compression and unchanged unreferenced images.
    monkeypatch.setattr(epub, "optimize_image", lambda data, name: b"optimized")
    entries = epub.assemble_epub(sample_inputs(), MODIFIED, split_level=parse_args(["--split-level", "none"]).split_level)
    expected = {
        "mimetype": "e468e350d1143eb648f60c7b0bd6031101ec0544a361ca74ecef256ac901f48b",
        "META-INF/container.xml": "6f9447704c84aa7f32b3a30df26f5acc08e669de7828c98c8dedfbed4fdbed92",
        "OPS/package.opf": "b9036c6f011d7c23c57b8e4fbf1b5cbdac2a1f2bb9dccb602291a4b237de2da0",
        "OPS/titlepage.xhtml": "7e01168c1b0268b71f56e94d200a7396a2c0fbec4d570a64d7b95bd4f54d1e79",
        "OPS/s00000-one.xhtml": "f3e8ede76f040937cd8a35c18dfdce6272997aa1fc0975ec8600890e6e1bcef9",
        "OPS/s00001-two.xhtml": "3d9447c8b5d69b53a47af4c0d1c7d989a9000c814788887c280de16620ce772b",
        "OPS/images/big.png": sha256(b"optimized").hexdigest(),
        "OPS/TOC.xhtml": "b1697f991d4b0540ad34513b310041dd7520240a53eaef4249bf4d213f1d485d",
        "OPS/toc.ncx": "6f1eb97534738a7e3ac347fce56f9825d25d6af02d35aa5da2c2617f79cc5f02",
        "OPS/images/unused.png": sha256(sample_inputs().images["unused.png"]).hexdigest(),
        "OPS/css/style.css": "10a696da98860010ec8a964eb369171b9128f5a7fb15639a964cb94ab6c3035f",
        "OPS/css/extra.css": "806db221261eade44c886da5317adb894822d146f0f69ed009e59cae83afcbd6",
    }
    assert [name for name, _ in entries] == list(expected)
    assert {name: _stable_digest(name, data) for name, data in entries} == expected


def _stable_digest(name, data):
    # Python 3.13's minidom stopped escaping '"' in text nodes; normalise that
    # one version-dependent difference so the golden hash holds on 3.11-3.13.
    if name == "OPS/package.opf":
        data = data.replace(b"&quot;", b'"')
    return sha256(data).hexdigest()


def split_book(markdown):
    inputs = sample_inputs()
    inputs.chapter_markdown["one.md"] = markdown
    entries = dict(epub.assemble_epub(inputs, MODIFIED))
    xml = {name: ET.fromstring(data) for name, data in entries.items()
           if name.endswith((".xhtml", ".opf", ".ncx", ".xml"))}
    return entries, xml


def assert_link_target(xml, href, source):
    filename, separator, anchor = href.partition("#")
    target = f"OPS/{unquote(filename)}" if filename else source
    assert target in xml
    if separator:
        assert any(element.get("id") == unquote(anchor) for element in xml[target].iter())


def test_nested_navigation_and_section_order_with_slug_and_id_collisions():
    entries, xml = split_book("""# Part I

## Chapter 1

Content with $x$.

### Café & pão

#### Detail

<p id="h-cafe-pao">Existing ID</p>

### Cafe & pão

## Chapter 1

More content.

### Another topic

![f](nested/BIG.PNG)
""")
    names = ["s00000-part-i.xhtml", "s00001-chapter-1.xhtml", "s00002-chapter-1-2.xhtml", "s00003-two.xhtml"]
    package = xml["OPS/package.opf"]
    items = package.findall("./{*}manifest/{*}item")
    chapters = [item for item in items if item.get("id").startswith("s")]
    assert [item.get("href") for item in chapters] == names
    assert [item.get("properties") for item in chapters] == [None, "mathml", None, None]
    assert [ref.get("idref") for ref in package.findall("./{*}spine/{*}itemref")] == [
        "titlepage", "s00000", "s00001", "s00002", "s00003",
    ]
    assert [name for name in entries if name in {f"OPS/{href}" for href in names}] == [
        f"OPS/{href}" for href in names
    ]
    assert Image.open(io.BytesIO(entries["OPS/images/big.png"])).size == (1800, 60)
    assert entries["OPS/images/unused.png"] == sample_inputs().images["unused.png"]
    assert xml["OPS/s00002-chapter-1-2.xhtml"].find(".//{*}img").get("src") == "images/big.png"

    nav = xml["OPS/TOC.xhtml"].find(".//{*}nav/{*}ol")
    roots = nav.findall("{*}li")
    assert [node.find("{*}a").text for node in roots] == ["Part I", "Two"]
    children = roots[0].findall("{*}ol/{*}li")
    assert [node.find("{*}a").text for node in children] == ["Chapter 1", "Chapter 1"]
    topics = children[0].findall("{*}ol/{*}li")
    assert [node.find("{*}a").text for node in topics] == ["Café & pão", "Cafe & pão"]
    assert topics[0].find("{*}ol/{*}li/{*}a").text == "Detail"
    heading_targets = [node.find("{*}a").get("href") for node in topics]
    assert heading_targets == [
        "s00001-chapter-1.xhtml#h-cafe-pao-2", "s00001-chapter-1.xhtml#h-cafe-pao-3",
    ]
    ids = [e.get("id") for e in xml["OPS/s00001-chapter-1.xhtml"].iter() if e.get("id")]
    assert len(ids) == len(set(ids))

    ncx = xml["OPS/toc.ncx"]
    assert ncx.find("./{*}head/{*}meta[@name='dtb:depth']").get("content") == "4"
    part = ncx.find("./{*}navMap/{*}navPoint")
    assert len(part.findall("{*}navPoint")) == 2
    assert part.find("{*}navPoint/{*}navPoint/{*}navPoint/{*}navLabel/{*}text").text == "Detail"
    points = ncx.findall(".//{*}navPoint")
    links = nav.findall(".//{*}a")
    assert [p.get("playOrder") for p in points] == [str(i) for i in range(1, len(links) + 1)]
    assert [p.find("{*}navLabel/{*}text").text for p in points] == [a.text for a in links]
    assert [p.find("{*}content").get("src") for p in points] == [a.get("href") for a in links]
    for a in links:
        assert_link_target(xml, a.get("href"), "OPS/TOC.xhtml")


def test_cross_section_footnote_references_and_backlinks():
    _, xml = split_book("""# First

First reference[^1].

# Second

Repeated reference[^1].

[^1]: The shared note.
""")
    first = "OPS/s00000-first.xhtml"
    second = "OPS/s00001-second.xhtml"
    refs = [xml[name].find(".//{*}a[@class='footnote-ref']").get("href") for name in (first, second)]
    assert refs == ["s00001-second.xhtml#fn:1", "#fn:1"]
    note = xml[second].find(".//{*}li[@id='fn:1']")
    assert "The shared note." in "".join(note.itertext())
    backlinks = [a.get("href") for a in note.findall(".//{*}a[@class='footnote-backref']")]
    assert len(backlinks) == 2
    assert backlinks[0].startswith("s00000-first.xhtml#")
    assert backlinks[1].startswith("#")
    for source, href in list(zip([first, second], refs)) + [(second, link) for link in backlinks]:
        assert_link_target(xml, href, source)


def test_cli_defaults_to_auto_and_accepts_numeric_rank():
    assert parse_args([]).split_level == "auto"
    assert parse_args(["--split-level", "4"]).split_level == "4"


def test_build_reads_marker_toc_as_optional_hints(tmp_path):
    (tmp_path / "book.md").write_text("# Title\n\n## First\n\n## Second", encoding="utf-8")
    metadata = tmp_path / "book_metadata.json"
    description = BookDescription.for_workspace(tmp_path)
    output = tmp_path / "book.epub"
    for heading_level, expected in [(None, 1), (2, 3)]:
        metadata.write_text(json.dumps({"table_of_contents": [
            {"title": title, "heading_level": heading_level} for title in ["First", "Second"]
        ]}), encoding="utf-8")
        epub.build_epub(tmp_path, output, description)
        with zipfile.ZipFile(output) as archive:
            assert len([name for name in archive.namelist() if name.startswith("OPS/s000")]) == expected
