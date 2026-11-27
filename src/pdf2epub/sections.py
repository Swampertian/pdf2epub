"""Split a rendered Markdown document at top-level XHTML headings."""
import re
import unicodedata
from dataclasses import dataclass, field
from html.entities import html5
from urllib.parse import quote, unquote
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

SPLIT_LEVELS = ("auto", "1", "2", "3", "4", "5", "6", "none")
_HEADING = re.compile(r"h([1-6])\Z")
_SPACED = re.compile(r"(?<!\w)[^\W\d_](?:\s+[^\W\d_]){2,}(?!\w)")
_KIND = re.compile(r"^(introdu[çc][ãa]o|introduction|parte|part|cap[íi]tulo|chapter)\b", re.I)
_ROMAN = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
_VOID = re.compile(
    r'<(?:area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)'
    r'''(?=[\s/>])(?:[^>"']|"[^"]*"|'[^']*')*>''', re.I,
)
_RAW_MARKUP = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|\&(?!amp;|lt;|gt;|quot;|apos;)(\w+;)|" + _VOID.pattern,
                         re.S | re.I)


def normalize_label(text: str) -> str:
    """Collapse letter-spaced runs; keep a recognizable Roman Part number."""
    def collapse(match: re.Match) -> str:
        letters = "".join(match[0].split())
        if not letters.isupper():
            return match[0]
        part = re.fullmatch(r"(PARTE|PART)([IVXLCDM]+)(.*)", letters)
        if part and _ROMAN.fullmatch(part[2]):
            return " ".join(piece for piece in part.groups() if piece)
        return letters

    return " ".join(_SPACED.sub(collapse, text).split())


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:48].rstrip("-") or "section"


def unique_name(base: str, used: set[str]) -> str:
    """Return an unused name; callers own and update their name sets."""
    name, suffix = base, 2
    while name in used:
        name = f"{base}-{suffix}"
        suffix += 1
    return name


@dataclass(frozen=True)
class Heading:
    title: str
    level: int
    anchor: str


@dataclass
class Section:
    title: str
    level: int
    nodes: list[Node] = field(default_factory=list)
    subheadings: list[Heading] = field(default_factory=list)


def _repair_markup(match: re.Match) -> str:
    markup = match[0]
    if markup.startswith("&"):
        return "".join(f"&#{ord(c)};" for c in html5.get(match[1], markup))
    if markup.startswith("<!") or markup.endswith("/>"):
        return markup
    return markup[:-1] + "/>"


def _parse_body(body: str) -> minidom.Element:
    wrapped = f'<body xmlns:epub="http://www.idpf.org/2007/ops" xmlns:m="http://www.w3.org/1998/Math/MathML">{body}</body>'
    try:
        return minidom.parseString(wrapped).documentElement
    except ExpatError:
        # Marker emits raw HTML breaks in its Markdown tables.
        return minidom.parseString(_RAW_MARKUP.sub(_repair_markup, wrapped)).documentElement


def _text(node: Node) -> str:
    if node.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
        return node.data
    if node.nodeName == "br":
        return " "
    return "".join(_text(child) for child in node.childNodes)


def _is_quote(title: str) -> bool:
    return title.startswith(('"', "'", "“", "”", "‘", "’", "«", "»", "„", "‹", "›"))


def _headings(body: minidom.Element) -> dict[int, Heading]:
    ids = {node.getAttribute("id") for node in body.getElementsByTagName("*") if node.hasAttribute("id")}
    candidates = [
        (index, node, int(match[1]), title)
        for index, node in enumerate(body.childNodes)
        if (match := _HEADING.fullmatch(node.nodeName)) and (title := normalize_label(_text(node)))
    ]
    heading_nodes = {node for _, node, _, _ in candidates}
    seen = {
        node.getAttribute("id")
        for node in body.getElementsByTagName("*")
        if node not in heading_nodes and node.hasAttribute("id")
    }
    headings = {}
    for index, node, level, title in candidates:
        anchor = node.getAttribute("id")
        if not anchor or anchor in seen:
            anchor = unique_name(f"h-{slug(title)}", ids)
            node.setAttribute("id", anchor)
            ids.add(anchor)
        seen.add(anchor)
        if not _is_quote(title):
            headings[index] = Heading(title, level, anchor)
    return headings


def _kind(title: str) -> str:
    match = _KIND.match(title)
    if not match:
        return ""
    keyword = match[0].casefold()
    if keyword.startswith("part"):
        return "part"
    return "intro" if keyword.startswith("intro") else "chapter"


def _generic_boundaries(headings: dict[int, Heading], hints: set[tuple[str, int]]) -> dict[int, int]:
    levels = sorted({heading.level for heading in headings.values()})
    shallowest = levels[0]
    top = [i for i, heading in headings.items() if heading.level == shallowest]
    if len(top) == 1 and len(levels) > 1:
        # An isolated book title may precede chapters. Only promote the next
        # rank if Marker also identifies multiple headings there.
        peers = [i for i, h in headings.items() if i > top[0] and h.level == levels[1]]
        if sum((headings[i].title.casefold(), levels[1]) in hints for i in peers) >= 2:
            return {top[0]: 1, **dict.fromkeys(peers, 2)}
    return dict.fromkeys(top, 1)


def _boundaries(headings: dict[int, Heading], mode: str, hints: set[tuple[str, int]]) -> dict[int, int]:
    if mode != "auto":
        return {i: h.level for i, h in headings.items() if h.level <= int(mode)}
    kinds = {i: _kind(h.title) for i, h in headings.items()}
    if not any(kinds.values()):
        return _generic_boundaries(headings, hints)

    result = {}
    part = None
    implicit_level = None
    explicit_chapter = False
    for index, kind in kinds.items():
        heading = headings[index]
        if kind == "intro":
            result[index], part = 1, None
        elif kind == "part":
            result[index], part = 1, heading
            implicit_level, explicit_chapter = None, False
        elif kind == "chapter":
            result[index] = 2 if part else 1
            explicit_chapter = True
        elif part and not explicit_chapter and heading.level > part.level:
            if implicit_level is None:
                implicit_level = heading.level
            if heading.level == implicit_level:
                result[index] = 2
    return result


def _subtitles(nodes: list[Node], headings: dict[int, Heading], boundaries: dict[int, int]) -> dict[int, int]:
    result = {}
    for index in boundaries:
        heading = headings[index]
        if _kind(heading.title) not in ("intro", "chapter"):
            continue
        for following in range(index + 1, len(nodes)):
            node = nodes[following]
            if node.nodeType == Node.COMMENT_NODE or (node.nodeType == Node.TEXT_NODE and not node.data.strip()):
                continue
            subtitle = headings.get(following)
            if subtitle and subtitle.level > heading.level and following not in boundaries and not _kind(subtitle.title):
                result[index] = following
            break
    return result


def split_sections(body: str, fallback: str, mode: str = "auto",
                   hints: set[tuple[str, int]] | None = None) -> list[Section]:
    """Split the rendered document, keeping headings nested inside blocks intact.

    Auto ignores quote headings. Named introductions, parts and chapters take
    precedence over inconsistent hN ranks. Before the first named chapter in
    each part, the first deeper rank and its peers stand in for missing chapter
    labels. Merge an immediately following deeper subtitle into a named intro
    or chapter's label, without altering either heading's text. Otherwise,
    split at the shallowest usable rank (Marker's matching, non-null TOC levels
    can corroborate chapter peers under a lone title). A numeric mode splits
    at that rank and shallower. Preserve any preamble in the first section.
    """
    root = _parse_body(body)
    nodes = list(root.childNodes)
    headings = _headings(root)
    boundaries = _boundaries(headings, mode, hints or set()) if headings else {}
    if not boundaries:
        return [Section(fallback, 1, nodes)]
    subtitles = _subtitles(nodes, headings, boundaries) if mode == "auto" else {}
    sections = []
    starts = list(boundaries)
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(nodes)
        heading = headings[start]
        subtitle = subtitles.get(start)
        title = heading.title if subtitle is None else f"{heading.title} — {headings[subtitle].title}"
        level = boundaries[start]
        subheadings = [
            Heading(h.title, level + max(1, h.level - heading.level), h.anchor)
            for index in range(start + 1, end)
            if index != subtitle and (h := headings.get(index))
        ]
        sections.append(Section(title, level, nodes[start if i else 0:end], subheadings))
    return sections


def _elements(nodes: list[Node]):
    for node in nodes:
        if node.nodeType == Node.ELEMENT_NODE:
            yield node
            yield from node.getElementsByTagName("*")


def render_sections(sections: list[Section], hrefs: list[str]) -> list[str]:
    """Relocate local fragment links, including footnote references/backlinks."""
    targets = {}
    for section, href in zip(sections, hrefs, strict=True):
        for node in _elements(section.nodes):
            if node.hasAttribute("id"):
                targets.setdefault(node.getAttribute("id"), href)
    bodies = []
    for section, href in zip(sections, hrefs, strict=True):
        nodes = [node.cloneNode(deep=True) for node in section.nodes]
        for node in _elements(nodes):
            link = node.getAttribute("href")
            if link.startswith("#"):
                target = targets.get(unquote(link[1:]))
                if target and target != href:
                    node.setAttribute("href", f"{quote(target)}{link}")
        bodies.append("".join(node.toxml() for node in nodes))
    return bodies
