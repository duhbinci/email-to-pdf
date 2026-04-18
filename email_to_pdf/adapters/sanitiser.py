from __future__ import annotations

from email_to_pdf.domain.errors import SanitisationError
from email_to_pdf.infra.logging import get_logger

logger = get_logger(__name__)

_ALLOWED_TAGS = {
    "a",
    "abbr",
    "acronym",
    "address",
    "article",
    "aside",
    "b",
    "bdi",
    "bdo",
    "blockquote",
    "br",
    "caption",
    "center",
    "cite",
    "code",
    "col",
    "colgroup",
    "data",
    "dd",
    "del",
    "details",
    "dfn",
    "dir",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "font",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hgroup",
    "hr",
    "i",
    "img",
    "ins",
    "kbd",
    "legend",
    "li",
    "map",
    "mark",
    "menu",
    "menuitem",
    "nav",
    "ol",
    "p",
    "pre",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "section",
    "small",
    "span",
    "strike",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "time",
    "tr",
    "tt",
    "u",
    "ul",
    "var",
    "wbr",
}

_ALLOWED_ATTRS: dict[str, set[str]] = {
    "*": {"class", "style", "id", "dir", "lang", "title"},
    "a": {"href", "name", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan", "align", "valign"},
    "th": {"colspan", "rowspan", "align", "valign", "scope"},
    "col": {"span", "width"},
    "colgroup": {"span"},
    "table": {"border", "cellpadding", "cellspacing", "width", "align", "summary"},
    "font": {"color", "size", "face"},
    "ol": {"start", "type"},
    "li": {"value"},
    "bdo": {"dir"},
    "time": {"datetime"},
}


class Nh3SanitizerAdapter:
    def sanitise(self, html: str) -> str:
        try:
            import nh3
        except ImportError as exc:
            raise SanitisationError(
                "nh3 library is required for HTML sanitisation", cause=exc
            ) from exc

        try:
            clean_attrs: dict[str, set[str]] = {}
            for tag, attrs in _ALLOWED_ATTRS.items():
                clean_attrs[tag] = attrs

            result = nh3.clean(
                html,
                tags=_ALLOWED_TAGS,
                attributes=clean_attrs,
                link_rel=None,
                strip_comments=True,
            )
            return result
        except Exception as exc:
            raise SanitisationError(
                f"nh3 sanitisation failed: {exc}", cause=exc
            ) from exc
