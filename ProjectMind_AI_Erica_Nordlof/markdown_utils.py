from __future__ import annotations

import bleach
import mistune


ALLOWED_TAGS = {
    "p", "br", "strong", "em", "del", "blockquote", "code", "pre",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td", "hr", "a",
}
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "code": ["class"],
}
MARKDOWN = mistune.create_markdown(plugins=["table", "strikethrough"])


def render_markdown(text: str) -> str:
    rendered = MARKDOWN(text or "")
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return bleach.linkify(cleaned, callbacks=[_link_callback])


def _link_callback(attrs: dict[tuple[str | None, str], str], new: bool = False):
    href_key = (None, "href")
    if href_key in attrs:
        attrs[(None, "target")] = "_blank"
        attrs[(None, "rel")] = "noopener noreferrer"
    return attrs
