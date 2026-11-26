from xml.etree import ElementTree as ET

import pytest

from pdf2epub.html import chapter_body
from pdf2epub.sections import normalize_label, render_sections, split_sections


def split(markdown, mode="auto", hints=None):
    body, _ = chapter_body(markdown, [])
    return split_sections(body, "Fallback", mode, hints)


def test_auto_recovers_marker_chapters_and_keeps_epigraphs_in_body():
    parts = split("""### I N T R O D U Ç Ã O

#### *O mistério de Roseto*

### " A Q U E L A S P E S S O A S E S T A V A M M O R R E N D O D E V E L H I C E . N A D A M A I S . "

Introdução.

## P A R T E I O P O R T U N I D A D E

#### *O "efeito Mateus"*

Texto.

##### Um tópico dentro do capítulo

Texto.

#### *A regra das 10 mil horas*

# " E M H A M B U R G O T Í N H A M O S Q U E T O C A R D U R A N T E O I T O H O R A S . "

Texto.

### C A P Í T U L O 3

#### _O problema com os gênios – parte 1_

Texto.

#### Uma seção do capítulo
""")
    assert [(part.title, part.level) for part in parts] == [
        ("INTRODUÇÃO — O mistério de Roseto", 1),
        ("PARTE I OPORTUNIDADE", 1),
        ('O "efeito Mateus"', 2),
        ("A regra das 10 mil horas", 2),
        ("CAPÍTULO 3 — O problema com os gênios – parte 1", 2),
    ]
    assert [h.title for h in parts[2].subheadings] == ["Um tópico dentro do capítulo"]
    assert [h.title for h in parts[4].subheadings] == ["Uma seção do capítulo"]
    bodies = render_sections(parts, [f"{i}.xhtml" for i in range(len(parts))])
    intro = ET.fromstring(f"<body>{bodies[0]}</body>")
    assert [h.text for h in intro.findall("h3")] == [
        "I N T R O D U Ç Ã O",
        '" A Q U E L A S P E S S O A S E S T A V A M M O R R E N D O D E V E L H I C E . N A D A M A I S . "',
    ]
    assert intro.find("h4/em").text == "O mistério de Roseto"
    assert "E M H A M B U R G O" in bodies[3]


@pytest.mark.parametrize(("source", "label"), [
    ("C A P Í T U L O 3", "CAPÍTULO 3"),
    ("P A R T E I I O P O R T U N I D A D E", "PARTE II OPORTUNIDADE"),
    ("P A R T I C U L A R", "PARTICULAR"),
    ("  A história \n de um livro ", "A história de um livro"),
])
def test_normalize_label(source, label):
    assert normalize_label(source) == label


def test_numeric_threshold_and_nav_only_headings():
    parts = split("Preamble\n\n# First\n\n## Second\n\n### Topic\n\n#### Detail\n\n# “Quote”", "2")
    assert [(part.title, part.level) for part in parts] == [("First", 1), ("Second", 2)]
    assert [(h.title, h.level) for h in parts[1].subheadings] == [("Topic", 3), ("Detail", 4)]
    assert render_sections(parts, ["a.xhtml", "b.xhtml"])[0].startswith("<p>Preamble</p>")


@pytest.mark.parametrize("markdown", ["Just prose.", '# "A quote"', "> # A heading in a quote"])
def test_no_usable_heading_keeps_one_section(markdown):
    parts = split(markdown)
    assert [part.title for part in parts] == ["Fallback"]


def test_auto_uses_only_corroborating_toc_hints():
    source = "# Book title\n\n## First\n\n## Second"
    assert [part.title for part in split(source)] == ["Book title"]
    assert [part.title for part in split(source, hints={("first", 3), ("second", 2), ("ghost", 2)})] == [
        "Book title",
    ]
    assert [part.title for part in split(source, hints={("first", 2), ("second", 2), ("ghost", 2)})] == [
        "Book title", "First", "Second",
    ]


def test_html_breaks_and_named_entities_become_valid_xhtml():
    parts = split("## A &nbsp; heading\n\nHeading text<br>next line.")
    assert parts[0].title == "A heading"
    [body] = render_sections(parts, ["a.xhtml"])
    assert ET.fromstring(f"<body>{body}</body>").find("p/br").tail == "next line."
