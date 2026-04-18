from __future__ import annotations

import email
import email.header
import email.message
import email.policy
import email.utils
import re as _re
from datetime import datetime, timezone

import chardet

from email_to_pdf.adapters.parsers.mime_repair import ContentTypeCleaner
from email_to_pdf.domain.errors import EmlParseError
from email_to_pdf.domain.models import Address, Attachment, ParsedEmail
from email_to_pdf.infra.logging import get_logger

logger = get_logger(__name__)
_CLEANER = ContentTypeCleaner()
_MAX_DEPTH = 10
_HEADER_RE = _re.compile(rb"^[\x21-\x7e]+:[ \t]", _re.MULTILINE)


class EmlParserAdapter:
    def can_parse(self, data: bytes) -> bool:
        sample = data[:4096]
        return bool(_HEADER_RE.search(sample))

    def parse(self, data: bytes) -> ParsedEmail:
        try:
            msg = email.message_from_bytes(data, policy=email.policy.compat32)
        except Exception as exc:
            raise EmlParseError(f"Failed to parse EML bytes: {exc}", cause=exc) from exc

        warnings: list[str] = []
        html_body, text_body, attachments = self._walk(msg, depth=0, warnings=warnings)

        return ParsedEmail(
            message_id=self._decode_header(msg.get("Message-ID")),
            subject=self._decode_header(msg.get("Subject")) or "",
            from_=self._parse_address(self._decode_header(msg.get("From")) or ""),
            to=self._parse_addresses(self._decode_header(msg.get("To")) or ""),
            cc=self._parse_addresses(self._decode_header(msg.get("Cc")) or ""),
            bcc=self._parse_addresses(self._decode_header(msg.get("Bcc")) or ""),
            date=self._parse_date(msg.get("Date")),
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
            raw_headers=self._collect_raw_headers(msg),
            input_format="eml",
        )

    def _walk(
        self,
        msg: email.message.Message,
        depth: int,
        warnings: list[str],
    ) -> tuple[str | None, str | None, list[Attachment]]:
        if depth > _MAX_DEPTH:
            warnings.append(f"MIME depth cap reached at {_MAX_DEPTH}; skipping deeper parts")
            return None, None, []

        content_type = msg.get_content_type().lower()
        disposition = (msg.get("Content-Disposition") or "").lower()

        if content_type == "multipart/alternative":
            return self._handle_alternative(msg, depth, warnings)

        if content_type in ("multipart/mixed", "multipart/related", "multipart/report"):
            return self._handle_mixed(msg, depth, warnings)

        if content_type == "message/rfc822":
            inner = msg.get_payload(decode=False)
            if isinstance(inner, list) and inner:
                return self._walk(inner[0], depth + 1, warnings)
            return None, None, []

        if "attachment" in disposition:
            att = self._make_attachment(msg, is_inline=False)
            return None, None, [att] if att else []

        if content_type == "text/html":
            html = self._decode_part(msg, warnings)
            return html, None, []

        if content_type == "text/plain":
            text = self._decode_part(msg, warnings)
            return None, text, []

        if content_type.startswith("image/") or content_type.startswith("application/"):
            att = self._make_attachment(msg, is_inline=("inline" in disposition or bool(msg.get("Content-ID"))))
            return None, None, [att] if att else []

        return None, None, []

    def _handle_alternative(
        self,
        msg: email.message.Message,
        depth: int,
        warnings: list[str],
    ) -> tuple[str | None, str | None, list[Attachment]]:
        html_body: str | None = None
        text_body: str | None = None
        attachments: list[Attachment] = []

        for part in msg.get_payload():  # type: ignore[union-attr]
            if not isinstance(part, email.message.Message):
                continue
            h, t, a = self._walk(part, depth + 1, warnings)
            attachments.extend(a)
            if h:
                html_body = h
            if t and not text_body:
                text_body = t

        return html_body, text_body, attachments

    def _handle_mixed(
        self,
        msg: email.message.Message,
        depth: int,
        warnings: list[str],
    ) -> tuple[str | None, str | None, list[Attachment]]:
        html_body: str | None = None
        text_body: str | None = None
        attachments: list[Attachment] = []

        for part in msg.get_payload():  # type: ignore[union-attr]
            if not isinstance(part, email.message.Message):
                continue
            h, t, a = self._walk(part, depth + 1, warnings)
            attachments.extend(a)
            if h and not html_body:
                html_body = h
            if t and not text_body:
                text_body = t

        return html_body, text_body, attachments

    def _decode_part(self, msg: email.message.Message, warnings: list[str]) -> str | None:
        raw = msg.get_payload(decode=True)
        if not isinstance(raw, bytes):
            return None

        charset = msg.get_param("charset") or None
        charset = _CLEANER.clean_charset(charset)
        return self._decode_bytes(raw, charset, warnings)

    def _decode_bytes(self, data: bytes, charset: str, warnings: list[str]) -> str:
        for cs in [charset, "utf-8"]:
            try:
                return data.decode(cs)
            except (UnicodeDecodeError, LookupError):
                pass

        detected = chardet.detect(data)
        if detected.get("encoding"):
            try:
                return data.decode(detected["encoding"])
            except (UnicodeDecodeError, LookupError):
                pass

        return data.decode("latin-1", errors="replace")

    def _make_attachment(
        self, msg: email.message.Message, is_inline: bool
    ) -> Attachment | None:
        raw = msg.get_payload(decode=True)
        if not isinstance(raw, bytes):
            return None

        filename = msg.get_filename() or ""
        if not filename:
            filename = msg.get_param("name") or ""
        filename = self._decode_header(filename) or "unnamed"

        content_id = msg.get("Content-ID")
        if content_id:
            content_id = content_id.strip("<>")

        content_type = msg.get_content_type() or "application/octet-stream"

        return Attachment(
            content_id=content_id,
            filename=filename,
            content_type=content_type,
            data=raw,
            size=len(raw),
            is_inline=is_inline or bool(content_id),
        )

    def _decode_header(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parts = email.header.decode_header(value)
            decoded_parts = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    cs = charset or "utf-8"
                    try:
                        decoded_parts.append(part.decode(cs))
                    except (UnicodeDecodeError, LookupError):
                        decoded_parts.append(part.decode("latin-1", errors="replace"))
                else:
                    decoded_parts.append(part)
            return "".join(decoded_parts)
        except Exception:
            return value

    def _parse_address(self, value: str) -> Address:
        if not value:
            return Address(display_name="", addr_spec="")
        name, addr = email.utils.parseaddr(value)
        name = self._decode_header(name) or name
        return Address(display_name=name, addr_spec=addr)

    def _parse_addresses(self, value: str) -> list[Address]:
        if not value:
            return []
        addrs = email.utils.getaddresses([value])
        result = []
        for name, addr in addrs:
            name = self._decode_header(name) or name
            result.append(Address(display_name=name, addr_spec=addr))
        return result

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            logger.warning("malformed_date_header", value=value)
            return None

    def _collect_raw_headers(self, msg: email.message.Message) -> dict[str, list[str]]:
        headers: dict[str, list[str]] = {}
        for key, val in msg.items():
            headers.setdefault(key.lower(), []).append(val)
        return headers
