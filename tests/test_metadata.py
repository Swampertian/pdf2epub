from datetime import datetime

from pdf2epub.metadata import BookDescription, Chapter


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
