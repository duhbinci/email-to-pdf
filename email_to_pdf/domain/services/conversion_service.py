from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
import time
from typing import TYPE_CHECKING

import anyio

from email_to_pdf.domain.errors import (
    BrowserCrashError,
    EmlParseError,
    NormalisationError,
    ParseError,
    RenderError,
)
from email_to_pdf.domain.models import ConversionResult
from email_to_pdf.domain.services.html_normaliser import HtmlNormaliser
from email_to_pdf.infra.config import Settings
from email_to_pdf.infra.logging import get_logger

if TYPE_CHECKING:
    from email_to_pdf.ports import (
        EmailParserPort,
        HtmlRendererPort,
        SanitizerPort,
        StoragePort,
    )

logger = get_logger(__name__)


class ConversionService:
    def __init__(
        self,
        parsers: list[EmailParserPort],
        renderer: HtmlRendererPort,
        sanitizer: SanitizerPort,
        storage: StoragePort | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._parsers = parsers
        self._renderer = renderer
        self._sanitizer = sanitizer
        self._storage = storage
        self._settings = settings or Settings()
        self._normaliser = HtmlNormaliser()

    async def convert(
        self,
        data: bytes,
        job_id: str | None = None,
        output_key: str | None = None,
    ) -> ConversionResult:
        input_hash = hashlib.sha256(data).hexdigest()
        if job_id is None:
            job_id = input_hash[:16]

        log = logger.bind(job_id=job_id, input_hash=input_hash[:8])
        log.info("conversion_started", size=len(data))

        warnings: list[str] = []
        durations: dict[str, float] = {}
        extracted_attachments: list[str] = []

        t0 = time.monotonic()
        parser = await asyncio.to_thread(self._select_parser, data, job_id)
        durations["format_detection"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        try:
            parsed = await asyncio.to_thread(parser.parse, data)
        except ParseError:
            raise
        except Exception as exc:
            raise EmlParseError(
                f"Parse failed: {exc}", job_id=job_id, cause=exc
            ) from exc
        durations["parse"] = (time.monotonic() - t0) * 1000
        log.info("parse_complete", format=parsed.input_format)

        t0 = time.monotonic()
        html_body = parsed.html_body
        if html_body:
            try:
                html_body = await asyncio.to_thread(self._sanitizer.sanitise, html_body)
            except Exception as exc:
                warnings.append(f"SANITISATION_SKIPPED: {exc}")
                log.error("sanitisation_failed", error=str(exc))
        durations["sanitise"] = (time.monotonic() - t0) * 1000

        if html_body != parsed.html_body:
            parsed = dataclasses.replace(parsed, html_body=html_body)

        t0 = time.monotonic()
        try:
            normalised_html = await asyncio.to_thread(
                self._normaliser.build, parsed, self._settings.render, warnings
            )
        except Exception as exc:
            raise NormalisationError(
                f"HTML normalisation failed: {exc}", job_id=job_id, cause=exc
            ) from exc
        durations["normalise"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        try:
            pdf_bytes = await self._renderer.render(
                normalised_html, self._settings.render
            )
        except RenderError:
            raise
        except Exception as exc:
            raise BrowserCrashError(
                f"Render failed: {exc}", job_id=job_id, cause=exc
            ) from exc
        durations["render"] = (time.monotonic() - t0) * 1000
        log.info("render_complete", pdf_size=len(pdf_bytes))

        t0 = time.monotonic()
        if (
            self._settings.attachments.extract
            and self._settings.attachments.extract_directory
        ):
            extracted_attachments = await self._extract_attachments(
                parsed, job_id, warnings
            )
        if output_key and self._storage:
            await self._storage.write(output_key, pdf_bytes)
        durations["output"] = (time.monotonic() - t0) * 1000

        page_count = self._estimate_page_count(pdf_bytes)

        result = ConversionResult(
            job_id=job_id,
            input_hash=input_hash,
            pdf_bytes=pdf_bytes,
            page_count=page_count,
            output_size_bytes=len(pdf_bytes),
            extracted_attachments=extracted_attachments,
            warnings=warnings,
            stage_durations_ms=durations,
        )
        log.info("conversion_complete", page_count=page_count, warnings=len(warnings))
        return result

    def _select_parser(
        self, data: bytes, job_id: str | None = None
    ) -> "EmailParserPort":
        for parser in self._parsers:
            if parser.can_parse(data):
                return parser
        from email_to_pdf.domain.errors import UnsupportedFormatError

        raise UnsupportedFormatError(job_id=job_id)

    async def _extract_attachments(
        self, parsed: object, job_id: str, warnings: list[str]
    ) -> list[str]:
        from email_to_pdf.domain.models import ParsedEmail
        from email_to_pdf.domain.services.filename_sanitizer import FileNameSanitizer

        if not isinstance(parsed, ParsedEmail):
            return []

        extract_dir = self._settings.attachments.extract_directory
        if not extract_dir:
            return []

        sanitizer = FileNameSanitizer()
        used_names: set[str] = set()
        extracted: list[str] = []

        for i, att in enumerate(parsed.attachments):
            if i >= self._settings.attachments.max_count:
                warnings.append(
                    f"Attachment count exceeded max ({self._settings.attachments.max_count}); skipping remaining"
                )
                break
            if att.is_inline:
                continue
            try:
                safe_name = sanitizer.sanitise(att.filename or "unnamed", used_names)
                base = await anyio.Path(extract_dir).resolve()
                dest = await (base / safe_name).resolve()
                if not str(dest).startswith(str(base) + os.sep):
                    warnings.append(
                        f"Path traversal blocked for attachment: {att.filename!r}"
                    )
                    continue
                await dest.write_bytes(att.data)
                extracted.append(str(dest))
            except Exception as exc:
                warnings.append(f"Failed to extract attachment {att.filename!r}: {exc}")

        return extracted

    def _estimate_page_count(self, pdf_bytes: bytes) -> int:
        count = pdf_bytes.count(b"/Type /Page\n") + pdf_bytes.count(b"/Type/Page\n")
        if count == 0:
            count = max(1, pdf_bytes.count(b"endstream") // 3)
        return max(1, count)
