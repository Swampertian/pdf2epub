from datetime import datetime

from pdf2epub.metadata import BookDescription, Chapter, metadata_from_pdf_info


def test_round_trip_dict():
    data = {"metadata": {"dc:title": "T"}, "default_css": ["a.css"],
            "chapters": [{"markdown": "x.md", "css": ""}], "cover_image": None}
    assert BookDescription.from_dict(data).to_dict() == data


def test_for_workspace_defaults(tmp_path):
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a")
    d = BookDescription.for_workspace(tmp_path, now=datetime(2026, 1, 2, 3, 4, 5))
    assert [c.markdown for c in d.chapters] == ["a.md", "b.md"]
    assert d.identifier == "id-20260102030405"
    assert d.language == "en"


def test_css_files_dedup():
    d = BookDescription(chapters=[Chapter("a.md", "x.css"), Chapter("b.md", "x.css")])
    assert d.css_files() == ["style.css", "x.css"]


def test_metadata_from_pdf_info():
    info = {"Title": " Dom Casmurro ", "Author": "Machado de Assis",
            "CreationDate": "D:18991201120000+00'00'"}
    assert metadata_from_pdf_info(info) == {
        "dc:title": "Dom Casmurro", "dc:creator": "Machado de Assis", "dc:date": "1899-12-01"}


def test_metadata_from_pdf_info_skips_placeholders():
    for title in ("", "Untitled-1", "Microsoft Word - livro.docx", "scan0001.pdf"):
        assert "dc:title" not in metadata_from_pdf_info({"Title": title})
    assert metadata_from_pdf_info({"CreationDate": "garbage"}) == {}


def test_for_workspace_precedence(tmp_path):
    (tmp_path / "a.md").write_text("a")
    BookDescription(metadata={"dc:creator": "Saved Author"}).save(tmp_path)
    pdf = {"dc:title": "PDF Title", "dc:creator": "PDF Author"}
    d = BookDescription.for_workspace(tmp_path, pdf_metadata=pdf, fallback_title="file-stem")
    assert d.title == "PDF Title"
    assert d.authors == "Saved Author"


def test_for_workspace_title_falls_back_to_file_name(tmp_path):
    (tmp_path / "a.md").write_text("a")
    d = BookDescription.for_workspace(tmp_path, pdf_metadata={}, fallback_title="file-stem")
    assert d.title == "file-stem"
