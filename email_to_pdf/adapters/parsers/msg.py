from __future__ import annotations

import email.utils
from datetime import datetime, timezone

from email_to_pdf.domain.errors import MsgParseError
from email_to_pdf.domain.models import Address, Attachment, ParsedEmail
from email_to_pdf.infra.logging import get_logger

logger = get_logger(__name__)

_CFBF_MAGIC = b"\xd0\xcf\x11\xe0"


class MsgParserAdapter:
    def can_parse(self, data: bytes) -> bool:
        return data[:4] == _CFBF_MAGIC

    def parse(self, data: bytes) -> ParsedEmail:
        try:
            import extract_msg
        except ImportError as exc:
            raise MsgParseError(
                "extract-msg library is required for MSG parsing", cause=exc
            ) from exc

        import io
        warnings: list[str] = []

        try:
            msg_file = io.BytesIO(data)
            msg = extract_msg.Message(msg_file)
        except Exception as exc:
            raise MsgParseError(f"Failed to open MSG file: {exc}", cause=exc) from exc

        try:
            subject = self._safe_get(msg, "subject", warnings) or ""
            from_str = self._safe_get(msg, "sender", warnings) or ""
            to_str = self._safe_get(msg, "to", warnings) or ""
            cc_str = self._safe_get(msg, "cc", warnings) or ""
            bcc_str = self._safe_get(msg, "bcc", warnings) or ""
            message_id = self._safe_get(msg, "messageId", warnings)
            date = self._parse_date(msg, warnings)

            html_body = self._safe_get_body(msg, "htmlBody", warnings)
            text_body = self._safe_get_body(msg, "body", warnings)

            from_addr = self._parse_single_address(from_str)
            to_addrs = self._parse_address_list(to_str)
            cc_addrs = self._parse_address_list(cc_str)
            bcc_addrs = self._parse_address_list(bcc_str)

            attachments = self._extract_attachments(msg, warnings)

        except MsgParseError:
            raise
        except Exception as exc:
            raise MsgParseError(f"MSG extraction failed: {exc}", cause=exc) from exc
        finally:
            try:
                msg.close()
            except Exception:
                pass

        return ParsedEmail(
            message_id=message_id,
            subject=subject,
            from_=from_addr,
            to=to_addrs,
            cc=cc_addrs,
            bcc=bcc_addrs,
            date=date,
            html_body=html_body if html_body else None,
            text_body=text_body if text_body else None,
            attachments=attachments,
            raw_headers={},
            input_format="msg",
        )

    def _safe_get(self, msg: object, attr: str, warnings: list[str]) -> str | None:
        try:
            val = getattr(msg, attr, None)
            if val is None:
                return None
            if isinstance(val, bytes):
                return val.decode("utf-8", errors="replace")
            return str(val) if val else None
        except Exception as exc:
            warnings.append(f"Failed to read MSG field {attr!r}: {exc}")
            return None

    def _safe_get_body(self, msg: object, attr: str, warnings: list[str]) -> str | None:
        try:
            val = getattr(msg, attr, None)
            if val is None:
                return None
            if isinstance(val, bytes):
                try:
                    return val.decode("utf-8")
                except UnicodeDecodeError:
                    return val.decode("latin-1", errors="replace")
            return str(val) if val else None
        except Exception as exc:
            warnings.append(f"Failed to read MSG body field {attr!r}: {exc}")
            return None

    def _parse_date(self, msg: object, warnings: list[str]) -> datetime | None:
        try:
            dt = getattr(msg, "date", None)
            if dt is None:
                return None
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            if isinstance(dt, str):
                return email.utils.parsedate_to_datetime(dt)
            return None
        except Exception as exc:
            warnings.append(f"Failed to parse MSG date: {exc}")
            return None

    def _parse_single_address(self, value: str) -> Address:
        if not value:
            return Address(display_name="", addr_spec="")
        name, addr = email.utils.parseaddr(value)
        return Address(display_name=name or "", addr_spec=addr or value)

    def _parse_address_list(self, value: str) -> list[Address]:
        if not value:
            return []
        addrs = email.utils.getaddresses([value])
        return [Address(display_name=name or "", addr_spec=addr or "") for name, addr in addrs]

    def _extract_attachments(self, msg: object, warnings: list[str]) -> list[Attachment]:
        attachments: list[Attachment] = []
        try:
            raw_attachments = getattr(msg, "attachments", []) or []
            for att in raw_attachments:
                try:
                    data = getattr(att, "data", None)
                    if data is None:
                        long_filename = getattr(att, "longFilename", None)
                        short_filename = getattr(att, "shortFilename", None)
                        warnings.append(f"MSG attachment {long_filename or short_filename!r} has no data; skipping")
                        continue

                    if isinstance(data, str):
                        data = data.encode("utf-8")

                    filename = (
                        getattr(att, "longFilename", None)
                        or getattr(att, "shortFilename", None)
                        or "unnamed"
                    )
                    if not filename:
                        filename = "unnamed"

                    content_type = getattr(att, "mimetype", None) or "application/octet-stream"
                    content_id = getattr(att, "contentId", None)
                    if content_id:
                        content_id = content_id.strip("<>")

                    is_inline = bool(content_id) or (
                        getattr(att, "isInline", False) or False
                    )

                    attachments.append(
                        Attachment(
                            content_id=content_id,
                            filename=filename,
                            content_type=content_type,
                            data=data,
                            size=len(data),
                            is_inline=is_inline,
                        )
                    )
                except Exception as exc:
                    warnings.append(f"Failed to extract MSG attachment: {exc}")
        except Exception as exc:
            warnings.append(f"Failed to access MSG attachments: {exc}")

        return attachments
