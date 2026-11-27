from pdf2epub.html import convert_math_to_mathml, rewrite_image_refs


def math_count(html):
    return convert_math_to_mathml(html).count("<math")


def test_prices_are_not_math():
    assert math_count("<p>custa $5 e $10 hoje</p>") == 0


def test_inline_and_display_math():
    assert math_count("<p>seja $x$ e $a+b$</p>") == 2
    assert '<div class="math-display">' in convert_math_to_mathml("<p>$$E=mc^2$$</p>")


def test_escaped_dollar_is_literal():
    assert math_count(r"<p>\$a\$</p>") == 0


def test_code_blocks_are_untouched():
    html = "<pre><code>x = '$a$'</code></pre><code>$b$</code>"
    assert convert_math_to_mathml(html) == html


def test_image_refs_case_insensitive_and_missing():
    md = "![A](sub/FIG_1.PNG) ![B](missing.png)"
    refs = rewrite_image_refs(md, ["Fig_1.png"])
    assert refs.markdown == "![A](images/Fig_1.png) ![B](missing.png)"
    assert refs.referenced == ["Fig_1.png"]
    assert refs.missing == ["missing.png"]
