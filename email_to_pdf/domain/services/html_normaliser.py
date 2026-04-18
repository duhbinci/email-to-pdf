from __future__ import annotations

import base64
import html as _html
import re

from bs4 import BeautifulSoup

from email_to_pdf.domain.models import Attachment, ParsedEmail
from email_to_pdf.domain.services.header_renderer import HeaderRenderer
from email_to_pdf.infra.config import RenderSettings

_TRANSPARENT_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA"
    "DUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

_REMOTE_URL = re.compile(r"^https?://", re.IGNORECASE)
_CSS_CID_PATTERN = re.compile(r"url\(['\"]?cid:([^\"'\s>)]+)['\"]?\)", re.IGNORECASE)


class HtmlNormaliser:
    def __init__(self) -> None:
        self._header_renderer = HeaderRenderer()

    def build(
        self,
        email: ParsedEmail,
        settings: RenderSettings,
        warnings: list[str] | None = None,
    ) -> str:
        if warnings is None:
            warnings = []

        cid_map = self._build_cid_map(email.attachments)

        body_html = email.html_body
        if body_html:
            body_html = self._resolve_cids(body_html, cid_map, warnings)
            body_html = self._replace_remote_urls(body_html, warnings)
            body_html = self._truncate_if_needed(body_html, warnings)
        elif email.text_body:
            body_html = self._text_to_html(email.text_body)
        else:
            body_html = '<p style="color:#666;font-style:italic;">No body content</p>'

        header_html = self._header_renderer.render(email)
        page_css = self._build_page_css(settings)

        soup = BeautifulSoup(body_html, "html.parser")
        dir_attr = ""
        lang_attr = ""
        html_tag = soup.find("html")
        if html_tag:
            dir_attr = html_tag.get("dir", "")  # type: ignore[assignment]
            lang_attr = html_tag.get("lang", "")  # type: ignore[assignment]

        dir_str = f' dir="{dir_attr}"' if dir_attr else ""
        lang_str = f' lang="{lang_attr}"' if lang_attr else ""

        inner_body = self._extract_body_content(soup, body_html)

        document = f"""<!DOCTYPE html>
<html{dir_str}{lang_str}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
{page_css}
</style>
</head>
<body>
{header_html}
<div class="email-body">
{inner_body}
</div>
</body>
</html>"""
        return document

    def _build_cid_map(self, attachments: list[Attachment]) -> dict[str, Attachment]:
        cid_map: dict[str, Attachment] = {}
        for att in attachments:
            if att.content_id:
                clean = att.content_id.strip("<>").lower()
                cid_map[clean] = att
        return cid_map

    def _resolve_cids(
        self, html: str, cid_map: dict[str, Attachment], warnings: list[str]
    ) -> str:
        def replace_cid(match: re.Match[str]) -> str:
            cid = match.group(1).strip("<>").lower()
            att = cid_map.get(cid)
            if att:
                if att.size <= 10 * 1024 * 1024:
                    data_uri = self._attachment_to_data_uri(att)
                    return f'src="{data_uri}"'
                else:
                    warnings.append(
                        f"Attachment CID {cid!r} exceeds embed size limit; using placeholder"
                    )
                    return f'src="{_TRANSPARENT_PNG}"'
            warnings.append(f"Unresolved CID reference: {cid!r}; using placeholder")
            return f'src="{_TRANSPARENT_PNG}"'

        html = re.sub(
            r'src=["\']?cid:([^"\'>\s]+)["\']?',
            replace_cid,
            html,
            flags=re.IGNORECASE,
        )

        def replace_css_cid(match: re.Match[str]) -> str:
            cid = match.group(1).strip("<>").lower()
            att = cid_map.get(cid)
            if att and att.size <= 10 * 1024 * 1024:
                data_uri = self._attachment_to_data_uri(att)
                return f"url('{data_uri}')"
            warnings.append(f"Unresolved CSS CID reference: {cid!r}; using placeholder")
            return f"url('{_TRANSPARENT_PNG}')"

        html = _CSS_CID_PATTERN.sub(replace_css_cid, html)
        return html

    def _replace_remote_urls(self, html: str, warnings: list[str]) -> str:
        def replace_src(match: re.Match[str]) -> str:
            url = match.group(1)
            if _REMOTE_URL.match(url):
                warnings.append(f"Replaced remote URL {url!r} with placeholder")
                return f'src="{_TRANSPARENT_PNG}"'
            return match.group(0)

        return re.sub(
            r'src=["\']?(https?://[^"\'>\s]+)["\']?',
            replace_src,
            html,
            flags=re.IGNORECASE,
        )

    def _attachment_to_data_uri(self, att: Attachment) -> str:
        encoded = base64.b64encode(att.data).decode("ascii")
        return f"data:{att.content_type};base64,{encoded}"

    def _text_to_html(self, text: str) -> str:
        escaped = _html.escape(text)
        lines = escaped.split("\n")
        return "<br>\n".join(lines)

    def _truncate_if_needed(
        self, html: str, warnings: list[str], max_bytes: int = 20 * 1024 * 1024
    ) -> str:
        encoded = html.encode("utf-8")
        if len(encoded) > max_bytes:
            warnings.append(
                f"HTML body truncated from {len(encoded)} to {max_bytes} bytes"
            )
            truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
            return truncated + "\n<p>[truncated]</p>"
        return html

    def _build_page_css(self, settings: RenderSettings) -> str:
        return f"""\
@page {{ size: {settings.paper_format}; margin: {settings.margin_top_mm}mm {settings.margin_right_mm}mm {settings.margin_bottom_mm}mm {settings.margin_left_mm}mm; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }}"""

    def _extract_body_content(self, soup: BeautifulSoup, original_html: str) -> str:
        body = soup.find("body")
        if body:
            return body.decode_contents()
        return original_html
