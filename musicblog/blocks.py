"""Render Markdown into native Gutenberg blocks.

WordPress stores block posts as HTML annotated with ``<!-- wp:* -->`` comments.
Posting plain HTML works but collapses the whole report into a single "Classic"
block, so the Markdown is converted to HTML and then each top-level element is
wrapped in its matching block delimiter.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import markdown

#: Elements that never have a closing tag.
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}

_MARKDOWN_EXTENSIONS = ["extra", "sane_lists", "nl2br"]

#: Providers that get a real `wp:embed` block. A URL alone on its own line in
#: bericht.md becomes an embed; anything else stays a paragraph.
#: `aspect` adds the 16:9 responsive wrapper classes Gutenberg uses for video.
EMBED_PROVIDERS = {
    "youtube": {
        "hosts": ("youtube.com", "youtu.be"),
        "type": "video",
        "aspect": True,
    },
    "vimeo": {"hosts": ("vimeo.com",), "type": "video", "aspect": True},
    "spotify": {"hosts": ("open.spotify.com", "spotify.com"), "type": "rich", "aspect": False},
    "soundcloud": {"hosts": ("soundcloud.com",), "type": "rich", "aspect": False},
    "bandcamp": {"hosts": ("bandcamp.com",), "type": "rich", "aspect": False},
}

_URL_ONLY = re.compile(r'^(https?://[^\s<>"]+)$')
_ANCHOR_ONLY = re.compile(r'^<a\s+href="(https?://[^"]+)"[^>]*>\s*([^<]*?)\s*</a>$')

NGG_SHORTCODE_RE = re.compile(
    r"\n*<!-- wp:shortcode -->\s*\[ngg\b.*?\]\s*<!-- /wp:shortcode -->", re.DOTALL
)


class _Element:
    __slots__ = ("tag", "attrs", "inner")

    def __init__(self, tag: str | None, attrs: str, inner: str) -> None:
        self.tag = tag
        self.attrs = attrs
        self.inner = inner

    def open_tag(self, *, extra_class: str = "") -> str:
        attrs = self.attrs
        if extra_class:
            attrs = _with_class(attrs, extra_class)
        return f"<{self.tag}{attrs}>"


def _with_class(attrs: str, extra: str) -> str:
    match = re.search(r'\sclass="([^"]*)"', attrs)
    if match:
        merged = f"{match.group(1)} {extra}".strip()
        return attrs[: match.start()] + f' class="{merged}"' + attrs[match.end() :]
    return f'{attrs} class="{extra}"'


class _TopLevelSplitter(HTMLParser):
    """Split an HTML fragment into its top-level elements, keeping inner HTML verbatim."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.elements: list[_Element] = []
        self._depth = 0
        self._tag: str | None = None
        self._attrs = ""
        self._inner: list[str] = []

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _render_attrs(attrs: list[tuple[str, str | None]]) -> str:
        out = []
        for name, value in attrs:
            out.append(f" {name}" if value is None else f' {name}="{value}"')
        return "".join(out)

    def _emit(self, text: str) -> None:
        if self._depth:
            self._inner.append(text)

    def _close(self) -> None:
        self.elements.append(_Element(self._tag, self._attrs, "".join(self._inner)))
        self._tag, self._attrs, self._inner = None, "", []

    # -- HTMLParser hooks ------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        rendered = f"<{tag}{self._render_attrs(attrs)}>"
        if tag in _VOID:
            if self._depth:
                self._inner.append(rendered)
            else:
                self.elements.append(_Element(tag, self._render_attrs(attrs), ""))
            return
        if self._depth == 0:
            self._tag, self._attrs, self._inner = tag, self._render_attrs(attrs), []
            self._depth = 1
        else:
            self._inner.append(rendered)
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs) -> None:
        rendered = f"<{tag}{self._render_attrs(attrs)} />"
        if self._depth:
            self._inner.append(rendered)
        else:
            self.elements.append(_Element(tag, self._render_attrs(attrs), ""))

    def handle_endtag(self, tag: str) -> None:
        if self._depth == 0 or tag in _VOID:
            return
        self._depth -= 1
        if self._depth == 0:
            self._close()
        else:
            self._inner.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._inner.append(data)
        elif data.strip():
            # Bare text between blocks still deserves to be a paragraph.
            self.elements.append(_Element("p", "", data.strip()))

    def handle_entityref(self, name: str) -> None:
        self._emit(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._emit(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._emit(f"<!--{data}-->")


def _split(html: str) -> list[_Element]:
    parser = _TopLevelSplitter()
    parser.feed(html)
    parser.close()
    if parser._depth:  # unbalanced input -- keep what we have rather than losing it
        parser._close()
    return parser.elements


def block(name: str, inner: str, attrs: dict | None = None) -> str:
    """Wrap ``inner`` in a Gutenberg block comment pair."""
    suffix = f" {json.dumps(attrs, separators=(',', ':'), ensure_ascii=False)}" if attrs else ""
    if not inner:
        return f"<!-- wp:{name}{suffix} /-->"
    return f"<!-- wp:{name}{suffix} -->\n{inner}\n<!-- /wp:{name} -->"


def embed_provider(url: str) -> tuple[str, dict] | None:
    """Match a URL against :data:`EMBED_PROVIDERS` by hostname."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for slug, spec in EMBED_PROVIDERS.items():
        for candidate in spec["hosts"]:
            if host == candidate or host.endswith(f".{candidate}"):
                return slug, spec
    return None


def embed_block(url: str) -> str | None:
    """Build a Gutenberg embed block for a supported provider URL.

    WordPress resolves the oEmbed itself at render time -- the block only needs
    to carry the URL plus the provider metadata the editor expects.
    """
    match = embed_provider(url)
    if match is None:
        return None
    slug, spec = match
    classes = [
        "wp-block-embed",
        f"is-type-{spec['type']}",
        f"is-provider-{slug}",
        "wp-block-embed-" + slug,
    ]
    attrs = {
        "url": url,
        "type": spec["type"],
        "providerNameSlug": slug,
        "responsive": True,
    }
    if spec["aspect"]:
        aspect = "wp-embed-aspect-16-9 wp-has-aspect-ratio"
        attrs["className"] = aspect
        classes.extend(aspect.split())
    figure = (
        f'<figure class="{" ".join(classes)}"><div class="wp-block-embed__wrapper">\n'
        f"{url}\n"
        "</div></figure>"
    )
    return block("embed", figure, attrs)


def _paragraph_embed(inner: str) -> str | None:
    """If a paragraph is nothing but a supported URL, turn it into an embed."""
    text = inner.strip()
    for pattern in (_URL_ONLY, _ANCHOR_ONLY):
        found = pattern.match(text)
        if found:
            return embed_block(found.group(1))
    return None


def shortcode_block(shortcode: str) -> str:
    return block("shortcode", shortcode)


def gallery_shortcode(gallery_id: int, display: str = "basic_thumbnail") -> str:
    return f'[ngg src="galleries" ids="{gallery_id}" display="{display}"]'


def _render_element(element: _Element) -> str:
    tag, inner = element.tag, element.inner

    if tag == "p":
        embed = _paragraph_embed(inner)
        if embed:
            return embed
        return block("paragraph", f"<p{element.attrs}>{inner}</p>")

    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        # h1 is the post title in WordPress, so document h1s are demoted.
        level = max(2, int(tag[1]))
        attrs = {"level": level} if level != 2 else None
        return block("heading", f'<h{level}{_with_class(element.attrs, "wp-block-heading")}>{inner}</h{level}>', attrs)

    if tag in {"ul", "ol"}:
        items = "\n".join(
            block("list-item", f"<li{item.attrs}>{item.inner}</li>")
            for item in _split(inner)
            if item.tag == "li"
        )
        attrs = {"ordered": True} if tag == "ol" else None
        open_tag = element.open_tag(extra_class="wp-block-list")
        return block("list", f"{open_tag}\n{items}\n</{tag}>", attrs)

    if tag == "blockquote":
        return block("quote", f'<blockquote{_with_class(element.attrs, "wp-block-quote")}>\n{render_fragment(inner)}\n</blockquote>')

    if tag == "pre":
        code = inner if inner.lstrip().startswith("<code") else f"<code>{inner}</code>"
        return block("code", f'<pre{_with_class(element.attrs, "wp-block-code")}>{code}</pre>')

    if tag == "hr":
        return block("separator", '<hr class="wp-block-separator has-alpha-channel-opacity"/>')

    if tag == "img":
        return block("image", f'<figure class="wp-block-image"><img{element.attrs} /></figure>')

    if tag == "table":
        return block("table", f'<figure class="wp-block-table">{element.open_tag()}{inner}</table></figure>')

    closing = "" if tag in _VOID else f"</{tag}>"
    return block("html", f"{element.open_tag()}{inner}{closing}")


def render_fragment(html: str) -> str:
    """Wrap the top-level elements of an existing HTML fragment in blocks."""
    return "\n\n".join(_render_element(element) for element in _split(html))


def render(markdown_text: str) -> str:
    """Convert Markdown into Gutenberg block markup."""
    if not markdown_text.strip():
        return ""
    html = markdown.markdown(markdown_text, extensions=_MARKDOWN_EXTENSIONS, output_format="xhtml")
    return render_fragment(html)


def set_gallery_shortcode(content: str, gallery_id: int, display: str = "basic_thumbnail") -> str:
    """Append the gallery shortcode block, replacing any previous ngg block.

    Keeps re-runs idempotent: the post body ends with exactly one ngg shortcode.
    """
    content = NGG_SHORTCODE_RE.sub("", content).rstrip()
    appended = shortcode_block(gallery_shortcode(gallery_id, display))
    return f"{content}\n\n{appended}" if content else appended
