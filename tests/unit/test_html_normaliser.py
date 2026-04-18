from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from email_to_pdf.domain.models import Address, Attachment, ParsedEmail
from email_to_pdf.domain.services.html_normaliser import HtmlNormaliser, _TRANSPARENT_PNG
from email_to_pdf.infra.config import RenderSettings

_SETTINGS = RenderSettings()


def make_email(**kwargs: object) -> ParsedEmail:
    defaults: dict[str, object] = {
        "message_id": "<test@example.com>",
        "subject": "Test Email",
        "from_": Address(display_name="Sender", addr_spec="sender@example.com"),
        "to": [Address(display_name="Recipient", addr_spec="recipient@example.com")],
        "cc": [],
        "bcc": [],
        "date": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "html_body": "<p>Hello</p>",
        "text_body": None,
        "attachments": [],
        "raw_headers": {},
        "input_format": "eml",
    }
    defaults.update(kwargs)
    return ParsedEmail(**defaults)  # type: ignore[arg-type]


def make_attachment(
    content_id: str,
    data: bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,
    content_type: str = "image/png",
    filename: str = "image.png",
    is_inline: bool = True,
) -> Attachment:
    return Attachment(
        content_id=content_id,
        filename=filename,
        content_type=content_type,
        data=data,
        size=len(data),
        is_inline=is_inline,
    )


@pytest.fixture
def normaliser() -> HtmlNormaliser:
    return HtmlNormaliser()


class TestCidResolution:
    def test_cid_reference_resolved_to_data_uri(self, normaliser: HtmlNormaliser) -> None:
        img_data = b"fake_image_data"
        att = make_attachment(content_id="img001@example.com", data=img_data)
        email = make_email(
            html_body='<img src="cid:img001@example.com">',
            attachments=[att],
        )
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)

        expected_b64 = base64.b64encode(img_data).decode("ascii")
        assert f"data:image/png;base64,{expected_b64}" in result
        assert "cid:" not in result

    def test_cid_resolution_case_insensitive(self, normaliser: HtmlNormaliser) -> None:
        img_data = b"img_bytes"
        att = make_attachment(content_id="IMG@example.com", data=img_data)
        email = make_email(
            html_body='<img src="cid:img@example.com">',
            attachments=[att],
        )
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "cid:" not in result
        assert "data:image/png;base64," in result

    def test_missing_cid_replaced_with_transparent_placeholder(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(
            html_body='<img src="cid:missing@example.com">',
            attachments=[],
        )
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert _TRANSPARENT_PNG in result
        assert "cid:" not in result

    def test_missing_cid_produces_warning(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(
            html_body='<img src="cid:missing@example.com">',
            attachments=[],
        )
        warnings: list[str] = []
        normaliser.build(email, _SETTINGS, warnings)
        assert any("missing" in w.lower() or "unresolved" in w.lower() for w in warnings)

    def test_multiple_cid_references_resolved(self, normaliser: HtmlNormaliser) -> None:
        att1 = make_attachment(content_id="img1@example.com", data=b"data1")
        att2 = make_attachment(content_id="img2@example.com", data=b"data2")
        email = make_email(
            html_body='<img src="cid:img1@example.com"><img src="cid:img2@example.com">',
            attachments=[att1, att2],
        )
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "cid:" not in result
        assert result.count("data:image/png;base64,") >= 2


class TestRemoteUrlReplacement:
    def test_remote_http_url_replaced(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body='<img src="http://example.com/image.png">')
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "http://example.com/image.png" not in result
        assert _TRANSPARENT_PNG in result

    def test_remote_https_url_replaced(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body='<img src="https://example.com/logo.png">')
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "https://example.com/logo.png" not in result
        assert _TRANSPARENT_PNG in result

    def test_remote_url_replacement_produces_warning(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body='<img src="https://tracker.example.com/pixel.png">')
        warnings: list[str] = []
        normaliser.build(email, _SETTINGS, warnings)
        assert len(warnings) > 0

    def test_data_uri_not_replaced(self, normaliser: HtmlNormaliser) -> None:
        data_uri = "data:image/png;base64,abc123=="
        email = make_email(html_body=f'<img src="{data_uri}">')
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert data_uri in result


class TestPlainTextConversion:
    def test_plain_text_converted_to_html(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body=None, text_body="Hello World")
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "Hello World" in result
        assert "<html" in result.lower()

    def test_newlines_converted_to_br(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body=None, text_body="Line 1\nLine 2\nLine 3")
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "<br>" in result

    def test_html_special_chars_escaped_in_text(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body=None, text_body="<script>alert(1)</script>")
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestNoBody:
    def test_no_body_produces_stub_html(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body=None, text_body=None)
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "No body content" in result

    def test_no_body_still_has_header_block(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body=None, text_body=None, subject="Important Email")
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "Important Email" in result

    def test_no_body_is_valid_html(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(html_body=None, text_body=None)
        warnings: list[str] = []
        result = normaliser.build(email, _SETTINGS, warnings)
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result


class TestPrintCssInjection:
    def test_print_css_injected(self, normaliser: HtmlNormaliser) -> None:
        email = make_email()
        result = normaliser.build(email, _SETTINGS)
        assert "@page" in result

    def test_page_format_in_css(self, normaliser: HtmlNormaliser) -> None:
        settings = RenderSettings(paper_format="Letter")
        email = make_email()
        result = normaliser.build(email, settings)
        assert "Letter" in result


class TestRtlPreservation:
    def test_rtl_dir_attribute_preserved(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(
            html_body='<html dir="rtl"><body><p>مرحبا</p></body></html>'
        )
        result = normaliser.build(email, _SETTINGS)
        assert 'dir="rtl"' in result

    def test_lang_attribute_preserved(self, normaliser: HtmlNormaliser) -> None:
        email = make_email(
            html_body='<html lang="ar"><body><p>مرحبا</p></body></html>'
        )
        result = normaliser.build(email, _SETTINGS)
        assert 'lang="ar"' in result
