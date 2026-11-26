"""Pure Markdown -> XHTML body transformations (images, math)."""
from dataclasses import dataclass
from pathlib import Path

import latex2mathml.converter
import markdown
import regex as re

from .workspace import IMAGES_DIR

MARKDOWN_EXTENSIONS = ["codehilite", "tables", "fenced_code", "footnotes"]
MARKDOWN_EXTENSION_CONFIGS = {"codehilite": {"guess_lang": False}}

_IMAGE_REF = re.compile(r'!\[(.*?)\]\((.*?)\)')
_CODE_BLOCK = re.compile(r'<pre[\s\S]*?</pre>|<code[\s\S]*?</code>', flags=re.DOTALL)
_DISPLAY_PARAGRAPH = re.compile(r'<p>\s*\$\$(.*?)\$\$\s*</p>', flags=re.DOTALL)
_DISPLAY_INLINE = re.compile(r'\$\$(.*?)\$\$', flags=re.DOTALL)
# Inline $...$ follows pandoc's tex_math_dollars rules so prose like
# "costs $5 and $10" is left alone: the opening $ must be followed by a
# non-space, the closing $ preceded by a non-space and not followed by a
# digit, and the math may not span lines. \$ is a literal dollar.
_INLINE_MATH = re.compile(r'(?<![\\$])\$(?![\s$])([^\n$]*?[^\s\\$])\$(?![$\d])')


@dataclass(frozen=True)
class ImageRefs:
    markdown: str
    referenced: list[str]
    missing: list[str]


def rewrite_image_refs(markdown_text: str, available_images: list[str]) -> ImageRefs:
    """
    Point image references at images/<actual name>, matching by file name
    case-insensitively. References to unknown images are left unchanged.
    """
    lookup = {name.lower(): name for name in available_images}
    referenced, missing = [], []
    text = markdown_text
    for match in _IMAGE_REF.finditer(markdown_text):
        alt_text, image_path = match.groups()
        name = Path(image_path.strip()).name
        actual = lookup.get(name.lower())
        if actual is None:
            missing.append(name)
            continue
        referenced.append(actual)
        text = text.replace(match.group(0), f'![{alt_text}]({IMAGES_DIR}/{actual})')
    return ImageRefs(text, referenced, missing)


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(
        markdown_text,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs=MARKDOWN_EXTENSION_CONFIGS,
    )


def _latex_to_mathml(latex: str):
    try:
        return latex2mathml.converter.convert(latex)
    except Exception:
        return None


def _math_replacer(wrapper: str, css_class: str):
    def replace(match):
        mathml = _latex_to_mathml(match.group(1))
        return f'<{wrapper} class="{css_class}">{mathml}</{wrapper}>' if mathml else match.group(0)
    return replace


def convert_math_to_mathml(html_text: str) -> str:
    """Replace LaTeX math in HTML with MathML, skipping <pre>/<code> blocks."""
    placeholders = {}

    def mask(match):
        key = f"\x00MASK{len(placeholders)}\x00"
        placeholders[key] = match.group(0)
        return key

    text = _CODE_BLOCK.sub(mask, html_text)
    # Standalone display math wrapped in <p> becomes a <div> (a <div> inside
    # <p> would be invalid XHTML); display math inside phrasing content and
    # inline math use <span>.
    text = _DISPLAY_PARAGRAPH.sub(_math_replacer("div", "math-display"), text)
    text = _DISPLAY_INLINE.sub(_math_replacer("span", "math-display"), text)
    text = _INLINE_MATH.sub(_math_replacer("span", "math-inline"), text)
    for key, original in placeholders.items():
        text = text.replace(key, original)
    return text


def chapter_body(markdown_text: str, available_images: list[str]) -> tuple[str, ImageRefs]:
    """Markdown chapter -> XHTML body fragment plus its image references."""
    refs = rewrite_image_refs(markdown_text, available_images)
    return convert_math_to_mathml(markdown_to_html(refs.markdown)), refs
